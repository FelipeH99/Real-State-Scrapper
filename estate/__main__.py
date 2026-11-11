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
    run.add_argument('--pages',type=int,default=1,choices=range(1,11))
    run.add_argument('--delay',type=float,default=3)
    run.add_argument('--headed',action='store_true')
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
    args=p.parse_args();store=Store(args.db)
    if args.cmd=='collect':
        from .collect import collect
        config=json.loads((ROOT/'config/sources.json').read_text())
        unknown=set(args.sources)-set(config)
        if unknown: p.error(f'Sources unavailable for live collection: {unknown}')
        run,status=collect(store,config,args.sources,args.pages,args.delay,args.headed,ROOT/'data/captures')
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
        args.out.mkdir(parents=True,exist_ok=True)
        (args.out/'properties.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        columns=list(rows[0]) if rows else ['source','id','operation','price','currency','url']
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
