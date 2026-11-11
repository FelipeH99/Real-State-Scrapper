"""Conservative cross-portal duplicate candidates; never delete advertisements."""
import hashlib
import re
from collections import defaultdict
from .parsers import fold


def duplicate_groups(rows):
    buckets=defaultdict(list)
    for row in rows:
        ref=row.get('external_reference')
        if row['source']=='casasweb':ref=row['id'].upper()
        if ref and re.fullmatch(r'CW\d+',ref):
            buckets[('reference',row['operation'],ref)].append(row)
        address=fold(row.get('address'))
        if address and re.search(r'\b[1-9]\d{1,4}\b',address) and all(row.get(k) is not None for k in ('bedrooms','built_m2','price','currency')):
            address=re.sub(r'[^a-z0-9]+',' ',address).strip()
            key=('attributes',row['operation'],address,row['bedrooms'],row['built_m2'],row['price'],row['currency'])
            buckets[key].append(row)
    result=[]
    seen=set()
    for key,members in buckets.items():
        if len({r['source'] for r in members})<2:continue
        identity=tuple(sorted((r['source'],r['id'],r['operation']) for r in members))
        if identity in seen:continue
        seen.add(identity)
        result.append(dict(group='dup-'+hashlib.sha256(repr(identity).encode()).hexdigest()[:12],
            confidence='referencia compartida' if key[0]=='reference' else 'candidato: revisar',
            evidence='Referencia externa '+key[2] if key[0]=='reference' else 'Dirección, dormitorios, superficie, precio y moneda coinciden',
            members=[{k:r[k] for k in ('source','id','operation','url')} for r in members]))
    return result


def annotate_duplicates(rows):
    groups=duplicate_groups(rows)
    annotations={}
    for group in groups:
        for r in group['members']:
            annotations.setdefault((r['source'],r['id'],r['operation']),group)
    for row in rows:
        group=annotations.get((row['source'],row['id'],row['operation']),{})
        row['duplicate_group']=group.get('group')
        row['duplicate_confidence']=group.get('confidence')
    return groups
