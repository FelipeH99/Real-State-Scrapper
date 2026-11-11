"""Bounded collection. No persistent account, proxy, captcha solver or stealth."""
import json
import re
import time
from time import monotonic
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from .parsers import parse, LayoutError
from .storage import now

UA='RealEstateCollector/0.3'


def same_host(a,b):
    return urlparse(a).hostname == urlparse(b).hostname


class HttpClient:
    def __init__(self,delay=3):
        self.session=requests.Session()
        self.session.headers['User-Agent']=UA
        self.delay=max(2,delay)
        self.robots={}
        self.cache={}

    def get(self,url):
        if url in self.cache:
            return self.cache[url]
        origin=f'{urlparse(url).scheme}://{urlparse(url).netloc}'
        if origin not in self.robots:
            r=self.session.get(origin+'/robots.txt',timeout=30)
            robot=RobotFileParser()
            if r.status_code==404:
                robot.parse([])
            else:
                r.raise_for_status()
                robot.parse(r.text.splitlines())
            self.robots[origin]=robot
        robot=self.robots[origin]
        if not robot.can_fetch(UA,url):
            raise RuntimeError(f'robots.txt disallows {url}')
        time.sleep(max(self.delay,robot.crawl_delay(UA) or 0))
        r=self.session.get(url,timeout=30)
        r.raise_for_status()
        self.cache[url]=(r.text,r.url)
        return self.cache[url]


class AccessBlocked(RuntimeError):
    """The portal refused the request; changing selectors cannot fix access."""


def check_browser_access(url):
    path=urlparse(url).path.lower()
    if any(part in path for part in ('/account-verification','/login','/captcha','/challenge')):
        raise AccessBlocked('El portal exige iniciar sesión o completar una verificación; captura anónima detenida')


def remax_snapshot(page, operation):
    # Applying filters unconditionally can replace valid rent results with sales.
    # Wait for a stable, semantically valid page before touching the controls.
    def stable_snapshot():
        deadline=monotonic()+8
        previous=None
        last_error=LayoutError('RE/MAX: results did not stabilize')
        while monotonic()<deadline:
            html=page.content()
            try:
                rows=parse('remax',html,operation,page.url)
                signature=tuple(sorted((r['id'],r['price'],r['currency']) for r in rows))
                if signature==previous:
                    return html,page.url
                previous=signature
            except LayoutError as exc:
                last_error=exc
                previous=None
            page.wait_for_timeout(750)
        raise last_error
    try:
        return stable_snapshot()
    except LayoutError:
        page.get_by_role('button',name=re.compile(r'^filtros \(',re.I)).click()
        # Explicitly select the operation in the expanded filter panel.
        label='Alquiler' if operation=='alquiler' else 'Comprar'
        page.locator('button.toggle__button:visible').filter(has_text=re.compile(rf'^\s*{label}\s*$')).click()
        page.get_by_role('button',name='Ver resultados',exact=True).click()
        return stable_snapshot()


def save_failure(out, source, operation, index, url, page, exc, http_status):
    """Best-effort local diagnostics must never hide the original failure."""
    prefix=out/f'{source}-{operation}-{index+1}-error'
    details=dict(source=source, operation=operation, requested_url=url,
                 observed_at=now(), error_type=type(exc).__name__, error=str(exc),
                 http_status=http_status)
    if page:
        details['actual_url']=page.url
        for suffix, capture in (
            ('.html',lambda: prefix.with_suffix('.html').write_text(page.content(),encoding='utf-8')),
            ('.png',lambda: page.screenshot(path=str(prefix.with_suffix('.png')),timeout=5000)),
        ):
            try:
                capture()
                details[suffix[1:]]=prefix.with_suffix(suffix).name
            except Exception as diagnostic_error:
                details[suffix[1:]+'_error']=str(diagnostic_error)
    prefix.with_suffix('.json').write_text(json.dumps(details,ensure_ascii=False,indent=2))
    return prefix.with_suffix('.json')


def collect(store,config,sources,pages=1,delay=3,headed=False,output='data/captures'):
    run=store.start();client=HttpClient(delay)
    out=Path(output)/run;out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    pw=None;browser=None
    try:
        for source in sources:
            spec=config[source]
            for operation,seed in spec['urls'].items():
                page=None;context=None;url=seed;seen=set();index=0;http_status=None
                print(f'{source}/{operation}: iniciando captura',flush=True)
                try:
                    if spec['transport']=='browser':
                        if browser is None:
                            from playwright.sync_api import sync_playwright
                            pw=sync_playwright().start()
                            browser=pw.chromium.launch(headless=not headed)
                        # A new anonymous context per search, never the user's browser profile.
                        context=browser.new_context(locale='es-UY')
                        page=context.new_page()
                    for index in range(min(pages,spec.get('max_pages',1))):
                        if page:
                            time.sleep(max(2,delay))
                            response=page.goto(url,wait_until='domcontentloaded',timeout=45000)
                            http_status=response.status if response else None
                            if http_status in (401,403,429):
                                raise AccessBlocked(f'HTTP {http_status}; acceso rechazado por el portal, sin reintentos')
                            if http_status and http_status>=400:
                                raise RuntimeError(f'HTTP {http_status}; stopped without retries')
                            check_browser_access(page.url)
                            page.locator(spec['selector']).first.wait_for(state='visible',timeout=30000)
                            check_browser_access(page.url)
                            if source=='remax':
                                html,actual=remax_snapshot(page,operation)
                            else:
                                html=page.content();actual=page.url
                        else:
                            html,actual=client.get(url)
                        rows=parse(source,html,operation,actual)
                        fingerprint=tuple(sorted(r['id'] for r in rows))
                        if fingerprint in seen:
                            raise LayoutError('Repeated result page; pagination stopped')
                        seen.add(fingerprint)
                        stamp=now()
                        path=out/f'{source}-{operation}-{index+1}.html'
                        path.write_text(html,encoding='utf-8')
                        manifest.append(dict(source=source,operation=operation,url=actual,file=str(path.resolve()),observed_at=stamp))
                        store.save(run,rows,stamp)
                        store.page(run,source,operation,actual,'ok',len(rows))
                        print(f'{source}/{operation}: página {index+1}, {len(rows)} avisos guardados',flush=True)
                        if not page or index+1>=min(pages,spec.get('max_pages',1)): break
                        if source=='casasymas':
                            nxt=page.get_by_role('link',name=str(index+2),exact=True)
                        else:
                            nxt=page.get_by_role('link',name='Siguiente',exact=True)
                        if not nxt.count(): break
                        href=nxt.first.get_attribute('href')
                        if not href: break
                        target=urljoin(actual,href)
                        if not same_host(seed,target):
                            raise LayoutError('Pagination leaves configured host')
                        url=target
                except Exception as exc:
                    # Redirects can also happen after the initial document response.
                    if page:
                        try:check_browser_access(page.url)
                        except AccessBlocked as blocked:exc=blocked
                    try:
                        diagnostic=save_failure(out,source,operation,index,url,page,exc,http_status)
                    except Exception as diagnostic_error:
                        diagnostic=f'no disponible ({type(diagnostic_error).__name__})'
                    actual=page.url if page else url
                    store.page(run,source,operation,actual,'error',error=f'{type(exc).__name__}: {exc}; diagnóstico: {diagnostic}')
                    print(f'{source}/{operation}: {type(exc).__name__}: {exc}; diagnóstico: {diagnostic}',flush=True)
                finally:
                    if context: context.close()
    finally:
        if browser: browser.close()
        if pw: pw.stop()
        (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        status=store.finish(run)
    return run,status
