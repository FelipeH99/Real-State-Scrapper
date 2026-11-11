"""Bounded collection with optional explicitly selected local Mercado Libre profile."""
import json
import re
import time
from time import monotonic
from pathlib import Path
from itertools import product
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from .parsers import parse, LayoutError, fold
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


def casas_search(page, neighborhood=None, bedrooms=None):
    for label,value in [('Departamento','Montevideo'),('Tipo','Apartamento')]+([('Zona',neighborhood)] if neighborhood else []):
        control=page.get_by_label(label,exact=True)
        options=json.loads(control.get_attribute('data-autocomplete-options') or '[]')
        chosen=next((option for option in options if fold(option)==fold(value)),None)
        if chosen is None:raise LayoutError(f'Unsupported {label}: {value}')
        control.fill(chosen)
        page.locator('button[data-autocomplete-option]:visible').filter(has_text=re.compile(rf'^\s*{re.escape(chosen)}\s*$')).click()
    if bedrooms is not None:page.get_by_label('Dormitorios',exact=True).fill(str(bedrooms))
    with page.expect_navigation(wait_until='domcontentloaded',timeout=45000):
        page.locator('button[data-search-submit]:visible').click()
    page.locator('a.prop-entrada').first.wait_for(timeout=30000)


def collect(store,config,sources,pages=1,delay=3,headed=False,output='data/captures',
            use_ml_profile=False,neighborhoods=None,bedrooms=None,max_listings=1000):
    run=store.start();client=HttpClient(delay)
    out=Path(output)/run;out.mkdir(parents=True,exist_ok=True)
    manifest=[];summary=[];run_seen=set()
    pw=None;browser=None
    try:
        for source in sources:
            spec=config[source]
            partitions=list(product(neighborhoods or [None],bedrooms or [None])) if source=='casasymas' else [(None,None)]
            for (operation,seed),(neighborhood,beds) in product(spec['urls'].items(),partitions):
                if len(run_seen)>=max_listings:break
                page=None;context=None;url=seed;index=0;http_status=None;job_seen=set();in_page=False
                job=dict(source=source,operation=operation,neighborhood=neighborhood,bedrooms=beds,requested_pages=pages,page_limit=min(pages,spec.get('max_pages',1)),pages=0,new_records=0,stop='page_limit')
                job_id=len(summary)+1
                print(f'{source}/{operation}: iniciando captura ({neighborhood or "Montevideo"}, dormitorios={beds})',flush=True)
                try:
                    if spec['transport']=='browser':
                        if pw is None:
                            from playwright.sync_api import sync_playwright
                            pw=sync_playwright().start()
                        if source=='mercadolibre' and use_ml_profile:
                            from .session import PROFILE
                            PROFILE.mkdir(parents=True,exist_ok=True,mode=0o700)
                            context=pw.chromium.launch_persistent_context(str(PROFILE),headless=not headed,locale='es-UY')
                        else:
                            if browser is None:browser=pw.chromium.launch(headless=not headed)
                            context=browser.new_context(locale='es-UY')
                        page=context.new_page()
                    for index in range(min(pages,spec.get('max_pages',1))):
                        if page:
                            time.sleep(max(2,delay))
                            if not in_page:
                                response=page.goto(url,wait_until='domcontentloaded',timeout=45000)
                                http_status=response.status if response else None
                                if http_status in (401,403,429):raise AccessBlocked(f'HTTP {http_status}; acceso rechazado por el portal, sin reintentos')
                                if http_status and http_status>=400:raise RuntimeError(f'HTTP {http_status}')
                            check_browser_access(page.url)
                            page.locator(spec['selector']).first.wait_for(state='visible',timeout=30000)
                            if source=='casasymas' and index==0:
                                casas_search(page,neighborhood,beds)
                            check_browser_access(page.url)
                            if source=='remax':html,actual=remax_snapshot(page,operation)
                            else:html=page.content();actual=page.url
                        else:html,actual=client.get(url)
                        rows=parse(source,html,operation,actual)
                        if neighborhood:rows=[r for r in rows if fold(r.get('neighborhood'))==fold(neighborhood)]
                        if beds is not None:rows=[r for r in rows if r.get('bedrooms')==beds]
                        keys={(r['source'],r['id'],r['operation']) for r in rows}
                        if keys and not keys-job_seen:
                            job['stop']='repeated_results';break
                        job_seen.update(keys)
                        fresh=[r for r in rows if (r['source'],r['id'],r['operation']) not in run_seen]
                        fresh=fresh[:max_listings-len(run_seen)]
                        run_seen.update((r['source'],r['id'],r['operation']) for r in fresh)
                        stamp=now();path=out/f'{job_id}-{source}-{operation}-{index+1}.html'
                        path.write_text(html,encoding='utf-8')
                        manifest.append(dict(source=source,operation=operation,url=actual,file=str(path.resolve()),observed_at=stamp,
                                             records=len(rows),new_records=len(fresh),neighborhood=neighborhood,bedrooms=beds))
                        store.save(run,fresh,stamp)
                        store.page(run,source,operation,actual,'ok',len(fresh))
                        job['pages']+=1;job['new_records']+=len(fresh)
                        print(f'{source}/{operation}: página {index+1}, {len(rows)} coincidencias, {len(fresh)} nuevos en esta ejecución',flush=True)
                        if len(run_seen)>=max_listings:job['stop']='listing_limit';break
                        if not page or index+1>=min(pages,spec.get('max_pages',1)):break
                        if source=='remax':
                            nxt=page.locator('p.number').filter(has_text=re.compile(rf'^\s*{index+2}\s*$'))
                            if not nxt.count():job['stop']='last_page';break
                            nxt.click();page.wait_for_timeout(1500);url=page.url;in_page=True
                            continue
                        nxt=page.get_by_role('link',name=str(index+2) if source=='casasymas' else 'Siguiente',exact=True)
                        if not nxt.count():job['stop']='last_page';break
                        href=nxt.first.get_attribute('href')
                        if not href:job['stop']='last_page';break
                        target=urljoin(actual,href)
                        if not same_host(seed,target):raise LayoutError('Pagination leaves configured host')
                        url=target
                except Exception as exc:
                    if page:
                        try:check_browser_access(page.url)
                        except AccessBlocked as blocked:exc=blocked
                    try:diagnostic=save_failure(out,f'{job_id}-{source}',operation,index,url,page,exc,http_status)
                    except Exception as diagnostic_error:diagnostic=f'no disponible ({type(diagnostic_error).__name__})'
                    actual=page.url if page else url
                    store.page(run,source,operation,actual,'error',error=f'{type(exc).__name__}: {exc}; diagnóstico: {diagnostic}')
                    job.update(stop='error',error=f'{type(exc).__name__}: {exc}')
                    print(f'{source}/{operation}: {type(exc).__name__}: {exc}; diagnóstico: {diagnostic}',flush=True)
                finally:
                    summary.append(job)
                    if context:context.close()
    finally:
        if browser:browser.close()
        if pw:pw.stop()
        (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        (out/'summary.json').write_text(json.dumps(dict(records=len(run_seen),max_listings=max_listings,jobs=summary),ensure_ascii=False,indent=2))
        status=store.finish(run)
    return run,status
