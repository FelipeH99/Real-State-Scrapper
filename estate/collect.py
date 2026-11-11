"""Bounded collection. No persistent account, proxy, captcha solver or stealth."""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from .parsers import parse, LayoutError
from .storage import now

UA='RealEstateResearchPilot/0.2'


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


def collect(store,config,sources,pages=1,delay=3,headed=False,output='data/captures'):
    run=store.start();client=HttpClient(delay)
    out=Path(output)/run;out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    pw=None;browser=None
    try:
        for source in sources:
            spec=config[source]
            for operation,seed in spec['urls'].items():
                page=None;context=None;url=seed;seen=set()
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
                            if response and response.status>=400:
                                raise RuntimeError(f'HTTP {response.status}; stopped without retries')
                            page.locator(spec['selector']).first.wait_for(state='visible',timeout=30000)
                            if source=='remax':
                                page.get_by_role('button',name=re.compile(r'^filtros \(')).click()
                                page.get_by_role('button',name='Ver resultados',exact=True).click()
                                page.locator(spec['selector']).first.wait_for(state='visible',timeout=30000)
                                # Angular can show stale cards briefly during navigation.
                                page.wait_for_timeout(1500)
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
                    store.page(run,source,operation,url,'error',error=f'{type(exc).__name__}: {exc}')
                    print(f'{source}/{operation}: {type(exc).__name__}: {exc}')
                finally:
                    if context: context.close()
    finally:
        if browser: browser.close()
        if pw: pw.stop()
        (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        status=store.finish(run)
    return run,status
