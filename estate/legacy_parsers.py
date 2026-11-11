"""Offline parsers for imported InfoCasas and Casasweb captures.

These sources are not enabled for live collection.
"""
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

SOURCES = {'infocasas': 'https://www.infocasas.com.uy', 'casasweb': 'https://casasweb.com'}


def number(value):
    if value is None or value == '':
        return None
    if isinstance(value, (float, int)):
        return value
    m = re.search(r'\d[\d.,]*', str(value))
    return float(m[0].replace('.', '').replace(',', '.')) if m else None


def currency(value):
    return {'$': 'UYU', 'U$S': 'USD', 'USD': 'USD'}.get(value)


def text(node):
    return node.get_text(' ', strip=True) if node else ''


def parse_infocasas(html, operation):
    soup = BeautifulSoup(html, 'html.parser')
    payload = json.loads(soup.select_one('script#__NEXT_DATA__').string)
    listings = payload['props']['pageProps']['fetchResult']['searchFast']['data']
    for p in listings:
        if p['property_type']['name'] != 'Apartamento' or p['operation_type']['name'].lower() != operation:
            continue
        price, gc = p.get('price') or {}, p.get('commonExpenses') or {}
        fields = {x['field']: x['value'] for x in p.get('technicalSheet', [])}
        neighborhood = (p.get('locations', {}).get('neighbourhood') or [{}])[0].get('name')
        notes = []
        gc_amount = gc.get('amount') if not gc.get('hidePrice') and gc.get('amount', 0) > 0 else None
        if gc_amount is None:
            notes.append('GC no informado en campo estructurado; revisar descripción')
        description = text(BeautifulSoup(p.get('description') or '', 'html.parser'))
        match = re.search(r'gastos comunes\s*:?\s*\$\s*([\d.,]+)', description, re.I)
        if match and gc_amount is not None and currency((gc.get('currency') or {}).get('name')) == 'UYU' and number(match[1]) != gc_amount:
            notes.append('GC difiere entre ficha y descripción')
        if neighborhood == 'Parque Miramar':
            notes.append('Revisar departamento: portal lo incluye en Montevideo')
        if re.search(r'edificio.*aptos|oficina|traspaso|nuda', p.get('title', ''), re.I):
            notes.append('Revisar modalidad o tipología del aviso')
        yield dict(source='InfoCasas', id=str(p['id']), operation=operation.capitalize(),
                   neighborhood=neighborhood, type='Apartamento',
                   bedrooms=0 if fields.get('bedrooms') == 'Mono' else number(fields.get('bedrooms')), bathrooms=number(fields.get('bathrooms')),
                   built_m2=p.get('m2Built') or None, total_m2=None,
                   currency=currency((price.get('currency') or {}).get('name')),
                   price=price.get('amount') if not price.get('hidePrice') and price.get('amount', 0)>0 else None,
                   expenses_currency=currency((gc.get('currency') or {}).get('name')) if gc_amount is not None else None,
                   expenses=gc_amount, agency=(p.get('owner') or {}).get('name'),
                   title=p.get('title'), url=urljoin(SOURCES['infocasas'], p['link']), notes='; '.join(notes))


def parse_casasweb(html, operation):
    soup = BeautifulSoup(html, 'html.parser')
    for card in soup.select('.item-grid .card'):
        link = card.select_one('a[href*="_CW"]')
        if not link:
            continue
        label = text(card.select_one('.badge-zona-resultado'))
        if not label.startswith('Apartamento - '):
            continue
        price_node = next((x for x in card.select('.item-precio .precio')
                           if text(x.select_one('h3')).lower() == operation), None)
        if price_node is None:
            continue
        price_text = text(price_node.select_one('h2'))
        details = text(card.select_one('.item-det'))
        dorm = re.search(r'(\d+) Dormitorio', details)
        area = text(card.select_one('.tipo-propiedad-zona'))
        built = re.search(r'Edificados:\s*([\d.,]+)', area)
        total = re.search(r'Area Total:\s*([\d.,]+)', area)
        title = text(card.select_one('.item-title'))
        notes = ['Baños y GC no disponibles en tarjeta; falta consultar ficha']
        if built and total and number(built[1]) > number(total[1]):
            notes.append('Superficie edificada mayor que total en origen')
        if re.search(r'oficina|traspaso|nuda', title, re.I):
            notes.append('Revisar modalidad o tipología del aviso')
        yield dict(source='Casasweb', id=re.search(r'CW\d+', link['href'])[0],
                   operation=operation.capitalize(), neighborhood=label.split(' - ', 1)[1], type='Apartamento',
                   bedrooms=0 if 'Monoambiente' in details else number(dorm[1]) if dorm else None,
                   bathrooms=None, built_m2=number(built[1]) if built else None,
                   total_m2=number(total[1]) if total else None,
                   currency='USD' if 'USD' in price_text else 'UYU' if '$' in price_text else None,
                   price=number(price_text), expenses_currency=None, expenses=None,
                   agency=text(card.select_one('.card-footer')), title=title,
                   url=urljoin(SOURCES['casasweb'], link['href']), notes='; '.join(notes))
