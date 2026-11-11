"""Parse saved or rendered pages. Fail closed on unsupported listing layouts."""
import hashlib
import json
import re
import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class LayoutError(ValueError):
    pass


def txt(node):
    return node.get_text(' ', strip=True) if node else ''


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn').lower().strip()


def num(value, decimal_dot=False):
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return value
    m = re.search(r'\d[\d.,]*', str(value))
    if not m:
        return None
    v = m[0]
    if decimal_dot:
        return float(v.replace(',', ''))
    return float(v.replace('.', '').replace(',', '.'))


def money(value):
    currency = 'USD' if any(c in value for c in ('USD', 'U$S', 'US$', 'dólares')) else 'UYU' if any(c in value for c in ('UYU', '$', 'pesos')) else None
    return num(value), currency


def record(source, id, operation, **fields):
    return dict(source=source, id=str(id), operation=operation, type='Apartamento',
                **{k: fields.get(k) for k in ('title', 'neighborhood', 'address', 'department',
                    'bedrooms', 'bathrooms', 'built_m2', 'total_m2', 'price', 'currency',
                    'price_qualifier', 'expenses', 'expenses_currency', 'agency', 'url', 'notes')})


def require_scope(soup, operation):
    heading = fold(txt(soup.find('h1')))
    if operation not in heading or 'montevideo' not in heading:
        raise LayoutError(f'Filter not confirmed in heading: {heading!r}')


def casasymas(html, operation, url):
    s = BeautifulSoup(html, 'html.parser')
    require_scope(s, operation)
    cards = s.select('a.prop-entrada')
    if not cards:
        raise LayoutError('Casas y Más: page requires JavaScript or layout changed')
    rows = []
    for c in cards:
        location = c.select_one('.localidad_p')
        if not location or not txt(location).endswith('Apartamento'):
            continue
        pr = next((p for p in c.select('.precio-row') if fold(txt(p.select_one('.operacion'))) == operation), None)
        if pr is None:
            continue
        raw = pr.select_one('.js-price-value')
        if not raw or not raw.has_attr('data-price-raw'):
            raise LayoutError('Casas y Más: original price binding missing')
        # These attributes belong to the rendered price element, not a private API.
        price = num(raw['data-price-raw'], decimal_dot=True) if raw.get('data-price-hidden') == '0' else None
        currency = raw.get('data-price-currency')
        attrs = {}
        for li in c.select('.card-body li'):
            icon = li.find('img')
            if icon:
                attrs[icon.get('title')] = num(txt(li), decimal_dot=True)
        gc, gc_currency = money(txt(pr.select_one('.gastos-comunes')))
        notes = ['Precio original del elemento; la presentación puede convertirlo a otra moneda']
        if operation == 'alquiler' and currency == 'USD' and price and price >= 10000:
            notes.append('Precio/moneda inusual para alquiler; verificar ficha')
        rows.append(record('casasymas', c.get('data-impression-property-id') or c['href'], operation,
            title=txt(c.select_one('.titulo-prop')), neighborhood=txt(location.find('span')), department='Montevideo',
            bedrooms=attrs.get('Dormitorios'), bathrooms=attrs.get('Baños'), built_m2=attrs.get('Superficie Construida'),
            total_m2=attrs.get('Superficie'), price=price, currency=currency, price_qualifier='publicado',
            expenses=gc, expenses_currency=gc_currency, url=urljoin(url, c['href']), notes='; '.join(notes)))
    return rows


def campiglia(html, operation, url):
    s = BeautifulSoup(html, 'html.parser')
    cards = s.select('a[href*="propiedad/ampliada/"]')
    if not cards:
        raise LayoutError('Campiglia: no property cards')
    rows = []
    for c in cards:
        head = txt(c.find('h3'))
        if not re.search(rf'Apartamento en {operation}\b', head, re.I):
            continue
        data = [txt(x) for x in c.select('p.data')]
        if len(data) < 4:
            raise LayoutError('Campiglia: property fields changed')
        neighborhood = data[-2]
        # Catalog spans other departments; only confirmed Montevideo neighborhoods.
        if fold(neighborhood) not in {'puerto buceo','puerto del buceo','malvin','barrio sur','cordon','tres cruces','punta carretas','prado','atahualpa'}:
            continue
        price_match = re.search(r'(Desde|Alquiler)\s+(U\$S|\$)\s*([\d.,]+)', head)
        if not price_match:
            raise LayoutError('Campiglia: missing price label')
        bedrooms = num(data[-1])
        rows.append(record('campiglia', re.search(r'ampliada/(\d+)', c['href'])[1], operation,
            title=head, neighborhood=neighborhood.title(), department='Montevideo', address=data[0],
            bedrooms=bedrooms, price=num(price_match[3]), currency='USD' if price_match[2]=='U$S' else 'UYU',
            price_qualifier='desde' if price_match[1]=='Desde' else 'publicado', agency='Campiglia',
            url=urljoin(url, c['href']), notes='Baños, superficies y GC requieren ficha. Precio desde no equivale a precio cerrado.' if price_match[1]=='Desde' else 'Baños, superficies y GC requieren ficha.'))
    return rows


def remax(html, operation, url):
    s = BeautifulSoup(html, 'html.parser')
    require_scope(s, operation)
    cards = s.select('a.card-remax__href')
    if not cards:
        raise LayoutError('RE/MAX: no rendered cards')
    # Tested site bug: heading/filter stays set while results change to unrelated types/operations.
    contradictory = [c for c in cards if re.search(r'\b(casa|casas|terreno|lote|hectareas|oficina)\b',fold(txt(c.select_one('.card__description'))))
        or (operation == 'alquiler' and re.search(r'\bventa\b',fold(txt(c.select_one('.card__description')))))
        or (operation == 'venta' and re.search(r'\balquil',fold(txt(c.select_one('.card__description')))))]
    if contradictory:
        raise LayoutError(f'RE/MAX: {len(contradictory)} cards contradict filters; reject page')
    rows=[]
    for c in cards:
        price,currency=money(txt(c.select_one('.card__price')))
        gc,gcc=money(txt(c.select_one('.card__expenses')))
        text=txt(c)
        bedrooms = re.search(r'(\d+)\s+dormitorios', text)
        baths = re.search(r'(\d+)\s+baños',text)
        built = re.search(r'([\d.,]+)\s+m² cubiertos',text)
        total = re.search(r'([\d.,]+)\s+m² totales',text)
        link=urljoin(url,c['href'])
        rows.append(record('remax',link.rstrip('/').split('/')[-1],operation,
            title=txt(c.select_one('.card__description')), department='Montevideo',
            address=txt(c.select_one('.card__address')), neighborhood=txt(c.select_one('.card__ubication')) or None,
            bedrooms=0 if 'Monoambiente' in text else int(bedrooms[1]) if bedrooms else None,
            bathrooms=int(baths[1]) if baths else None,built_m2=num(built[1],True) if built else None,
            total_m2=num(total[1],True) if total else None,price=price,currency=currency,price_qualifier='publicado',
            expenses=gc,expenses_currency=gcc,agency=txt(c.select_one('.contact-person__info--office')),url=link,
            notes='Departamento según filtro del listado; barrio requiere ficha. No asumir disponibilidad.'))
    return rows


def mercadolibre(html, operation, url):
    s=BeautifulSoup(html,'html.parser')
    if 'montevideo' not in fold(txt(s)) or 'montevideo' not in url.lower():
        raise LayoutError('Mercado Libre: Montevideo filter not confirmed')
    cards=s.select('.poly-card__content')
    if not cards:
        raise LayoutError('Mercado Libre: no cards (blocked or layout changed)')
    rows=[]
    for c in cards:
        a=c.select_one('a.poly-component__title')
        if not a or 'apartamento.mercadolibre.com.uy/' not in a.get('href',''):
            continue  # Skip ad redirect links, not missing silently in documentation.
        if fold(txt(c.select_one('.poly-component__headline'))) != f'apartamento en {operation}':
            continue
        attrs=[txt(x) for x in c.select('.poly-attributes_list__item')]
        if any(re.search(r'\d+\s*(?:a|-)\s*\d+',x) for x in attrs):
            continue  # projects have ranges, are not individual units
        location=txt(c.select_one('.poly-component__location'))
        if 'montevideo' not in fold(location):
            continue
        title=txt(a)
        price_node=c.select_one('[aria-roledescription="Monto"]')
        price,currency=money(price_node.get('aria-label','') if price_node else '')
        bedroom=next((num(x) for x in attrs if 'dormitorio' in x),None)
        if bedroom is None and re.search(r'monoambiente|\bmono\b',fold(title)):
            bedroom=0
        link=a['href'].split('#')[0]
        parts=location.split(',')
        rows.append(record('mercadolibre',re.search(r'MLU-\d+',link)[0],operation,
            title=title,department='Montevideo',address=location,
            neighborhood=parts[-2].strip() if len(parts)>1 and fold(parts[-1])=='montevideo' else None,
            bedrooms=bedroom,bathrooms=next((num(x) for x in attrs if 'baño' in x),None),
            built_m2=next((num(x,True) for x in attrs if 'm² cubiertos' in x),None),
            total_m2=next((num(x,True) for x in attrs if 'm² totales' in x),None),
            price=price,currency=currency,price_qualifier='publicado',url=link,
            notes='GC e inmobiliaria requieren ficha. Muestra del listado; excluye enlaces publicitarios y proyectos con rangos.'))
    return rows


def legacy(html, operation, url, source):
    from .legacy_parsers import parse_infocasas, parse_casasweb
    fn=parse_infocasas if source=='infocasas' else parse_casasweb
    return [record(source,r['id'],operation,**{k:v for k,v in r.items() if k not in ('source','id','operation','type')},
                   department='Montevideo',price_qualifier='publicado') for r in fn(html,operation)]


PARSERS={'campiglia':campiglia,'casasymas':casasymas,'remax':remax,'mercadolibre':mercadolibre,
         'infocasas':lambda h,o,u:legacy(h,o,u,'infocasas'),'casasweb':lambda h,o,u:legacy(h,o,u,'casasweb')}


def parse(source, html, operation, url):
    rows=PARSERS[source](html,operation,url)
    if not rows:
        raise LayoutError(f'{source}: no matching apartments; do not overwrite existing data')
    unique={}
    for r in rows:
        if r['price'] is not None and (r['price'] < 0 or r['currency'] not in ('UYU','USD')):
            raise LayoutError(f'Invalid price/currency: {r["id"]}')
        unique[(r['id'],r['operation'])]=r
    return list(unique.values())
