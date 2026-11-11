"""Bounded detail enrichment, with separate timestamps from observed listing prices."""
import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
from .parsers import LayoutError, fold, money, num, txt
from .storage import now


def parse_casas_detail(html,row):
    soup=BeautifulSoup(html,'html.parser')
    heading=fold(txt(soup.select_one('.property-header .property-bread-links')) or txt(soup.find('h1')))
    operations={fold(txt(x)) for x in soup.select('.property-header .price-label')}
    if (row['operation'] not in heading and row['operation'] not in operations) or 'apartamento' not in heading or 'montevideo' not in heading:
        raise LayoutError('Detail heading does not confirm apartment, operation and Montevideo')
    fields={}
    neighborhood=txt(soup.select_one('.property-header .property-location span'))
    if neighborhood:fields['neighborhood']=neighborhood
    mapping={'dormitorios':'bedrooms','banos':'bathrooms','m² construidos':'built_m2','m² totales':'total_m2'}
    for item in soup.select('.feature-item'):
        label=fold(txt(item.select_one('.feature-label')))
        value=txt(item.select_one('.feature-value'))
        if label in mapping:fields[mapping[label]]=num(value,decimal_dot=',' not in value)
        if label=='gastos comunes':
            amount,currency=money(value)
            if amount is not None and currency:
                fields.update(expenses=amount,expenses_currency=currency)
    agency=txt(soup.select_one('.agency-badge-name'))
    if agency:fields['agency']=agency
    # Only an explicitly attributed external reference, never any incidental CW number.
    description=txt(soup.select_one('.description-content'))
    reference=re.search(r'Sincronizada desde Casasweb\.com ref:\s*(CW\d+)',description,re.I)
    if reference:fields['external_reference']=reference[1].upper()
    if not fields:raise LayoutError('No supported detail fields')
    return fields


def enrich(store,sources,limit=10,headed=False,output='data/details',operation=None):
    from playwright.sync_api import sync_playwright
    from .collect import check_browser_access,AccessBlocked,save_failure
    run=store.start();out=Path(output)/run;out.mkdir(parents=True,exist_ok=True)
    candidates=[r for r in store.rows() if r['source'] in sources and (operation is None or r['operation']==operation)]
    # Prioritize not-yet-enriched records; never refresh list-price timestamps here.
    candidates.sort(key=lambda r:(r.get('detail_observed_at') or '',r['source'],r['operation'],r['id']))
    report=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=not headed)
        try:
            page=browser.new_page(locale='es-UY')
            for i,row in enumerate(candidates[:limit]):
                http_status=None
                try:
                    time.sleep(3)
                    response=page.goto(row['url'],wait_until='domcontentloaded',timeout=45000)
                    http_status=response.status if response else None
                    if http_status and http_status>=400:raise AccessBlocked(f'HTTP {http_status}')
                    check_browser_access(page.url)
                    page.locator('.feature-item').first.wait_for(timeout=20000)
                    if not re.search(r'/propiedad/'+re.escape(row['id'])+r'(?:-|/|$)',page.url):
                        raise LayoutError('Detail redirected to a different property')
                    html=page.content();fields=parse_casas_detail(html,row)
                    file=out/f'{row["source"]}-{row["id"]}.html'
                    file.write_text(html)
                    store.save_details(row,fields,now())
                    store.page(run,row['source'],row['operation'],row['url'],'ok',1)
                    report.append(dict(source=row['source'],id=row['id'],fields=list(fields)))
                    print(f'Ficha {i+1}/{min(limit,len(candidates))}: {row["source"]}/{row["id"]}, {len(fields)} campos',flush=True)
                except Exception as exc:
                    save_failure(out,row['source'],row['operation'],i,row['url'],page,exc,http_status)
                    store.page(run,row['source'],row['operation'],row['url'],'error',error=str(exc))
                    print(f'Ficha {row["id"]}: {exc}',flush=True)
                    if isinstance(exc,AccessBlocked):break
        finally:
            browser.close()
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    status=store.finish(run)
    print(json.dumps(dict(run=run,status=status,details=len(report))))
    return 0 if status=='success' else 2
