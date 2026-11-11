import argparse
import csv
import json
from pathlib import Path

from .parsers import PARSERS, parse
from .storage import Store

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description='Inmuebles Montevideo: captura, historial y exportación')
    p.add_argument('--db',default=str(ROOT/'data/estate.sqlite3'))
    sub=p.add_subparsers(dest='cmd',required=True)
    run=sub.add_parser('collect',help='Run bounded anonymous collectors')
    run.add_argument('--sources',nargs='+',default=['campiglia'])
    run.add_argument('--pages',type=int,default=1,choices=range(1,51))
    run.add_argument('--delay',type=float,default=3)
    run.add_argument('--headed',action='store_true')
    run.add_argument('--use-ml-profile',action='store_true')
    run.add_argument('--neighborhoods',nargs='+')
    run.add_argument('--bedrooms',type=int,nargs='+')
    run.add_argument('--max-listings',type=int,default=1000)
    sub.add_parser('login',help='Open a separate local Mercado Libre profile for manual sign-in')
    detail=sub.add_parser('enrich',help='Read a bounded number of individual property pages')
    detail.add_argument('--sources',nargs='+',choices=['casasymas'],default=['casasymas'])
    detail.add_argument('--limit',type=int,default=10)
    detail.add_argument('--headed',action='store_true')
    detail.add_argument('--operation',choices=['venta','alquiler'])
    imp=sub.add_parser('import',help='Import captured HTML with original timestamps')
    imp.add_argument('manifest',type=Path)
    exp=sub.add_parser('export',help='Filtered JSON and Excel-compatible CSV')
    exp.add_argument('--out',type=Path,default=ROOT/'outputs/automated')
    exp.add_argument('--source',choices=list(PARSERS))
    exp.add_argument('--operation',choices=['venta','alquiler'])
    exp.add_argument('--neighborhood')
    exp.add_argument('--bedrooms',type=int)
    exp.add_argument('--currency',choices=['UYU','USD'])
    exp.add_argument('--max-price',type=float)
    sub.add_parser('status')
    sub.add_parser('changes')
    args=p.parse_args()
    if args.cmd=='login':
        from .session import login
        config=json.loads((ROOT/'config/sources.json').read_text())
        login(config['mercadolibre']['urls']['alquiler'])
        return 0
    store=Store(args.db)
    if args.cmd=='enrich':
        from .details import enrich
        if not 1<=args.limit<=100: p.error('--limit must be between 1 and 100')
        return enrich(store,args.sources,args.limit,args.headed,ROOT/'data/details',operation=args.operation)
    if args.cmd=='collect':
        from .collect import collect
        config=json.loads((ROOT/'config/sources.json').read_text())
        unknown=set(args.sources)-set(config)
        if unknown: p.error(f'Sources unavailable for live collection: {unknown}')
        if args.max_listings<1:p.error('--max-listings must be positive')
        if (args.neighborhoods or args.bedrooms) and args.sources!=['casasymas']:
            p.error('Partition filters currently require --sources casasymas')
        run,status=collect(store,config,args.sources,args.pages,args.delay,args.headed,ROOT/'data/captures',
            use_ml_profile=args.use_ml_profile,neighborhoods=args.neighborhoods,bedrooms=args.bedrooms,max_listings=args.max_listings)
        print(json.dumps(dict(run=run,status=status),indent=2))
        return 0 if status=='success' else 2
    if args.cmd=='import':
        run=store.start()
        for item in json.loads(args.manifest.read_text()):
            try:
                path=Path(item['file'])
                if not path.is_absolute():path=args.manifest.parent/path
                rows=parse(item['source'],path.read_text(),item['operation'],item['url'])
                store.save(run,rows,item['observed_at'])
                store.page(run,item['source'],item['operation'],item['url'],'ok',len(rows))
            except Exception as e:
                store.page(run,item['source'],item['operation'],item['url'],'error',error=str(e))
                print(f'{item["source"]}/{item["operation"]}: {e}')
        status=store.finish(run);print(json.dumps(dict(run=run,status=status)))
        return 0 if status=='success' else 2
    if args.cmd=='export':
        try:
            rows=store.rows(**{k:getattr(args,k) for k in ('source','operation','neighborhood','bedrooms','currency','max_price')})
        except ValueError as e:p.error(str(e))
        from .duplicates import annotate_duplicates
        duplicates=annotate_duplicates(rows)
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'duplicates.json').write_text(json.dumps(duplicates,ensure_ascii=False,indent=2))
        from collections import Counter
        coverage=dict(ads=len(rows),by_source_operation=[dict(source=s,operation=o,ads=n) for (s,o),n in sorted(Counter((r['source'],r['operation']) for r in rows).items())],
            enriched_ads=sum(bool(r.get('detail_observed_at')) for r in rows),duplicate_groups=len(duplicates),
            note='Avisos por fuente; no representa inmuebles únicos ni cobertura total del mercado.')
        (args.out/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
        (args.out/'properties.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        columns=list(dict.fromkeys(k for r in rows for k in r)) if rows else ['source','id','operation','price','currency','url']
        with (args.out/'properties.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
            for r in rows:
                w.writerow({k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in r.items()})
        (args.out/'changes.json').write_text(json.dumps(store.changes(),ensure_ascii=False,indent=2))
        (args.out/'runs.json').write_text(json.dumps(store.status(),indent=2))
        print(f'{len(rows)} records exported to {args.out.resolve()}')
    elif args.cmd=='changes':print(json.dumps(store.changes(),ensure_ascii=False,indent=2))
    elif args.cmd=='status':print(json.dumps(store.status(),indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
