"""One manual collection/export cycle, with a process lock and honest exit status."""
import argparse
import fcntl
import os
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=root/'data/estate.sqlite3')
    parser.add_argument('--out',type=Path,default=root/'outputs/automated')
    parser.add_argument('--sources',nargs='+',default=['campiglia','casasymas','remax'])
    parser.add_argument('--pages',type=int,choices=range(1,51),default=1)
    parser.add_argument('--delay',type=float,default=3)
    parser.add_argument('--headed',action='store_true')
    parser.add_argument('--use-ml-profile',action='store_true')
    parser.add_argument('--neighborhoods',nargs='+')
    parser.add_argument('--bedrooms',type=int,nargs='+')
    parser.add_argument('--max-listings',type=int,default=1000)
    parser.add_argument('--details',type=int,default=0,choices=range(0,101))
    args=parser.parse_args()
    # Resolve before changing cwd, so user-provided relative paths stay meaningful.
    database=args.db.resolve();output=args.out.resolve()
    os.chdir(root)
    (root/'data').mkdir(exist_ok=True)
    with (root/'data/run.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Ya hay una captura en ejecución.')
        base=[sys.executable,'-u','-m','estate','--db',str(database)]
        options=['--sources',*args.sources,'--pages',str(args.pages),'--delay',str(args.delay)]
        if args.headed:options.append('--headed')
        if args.use_ml_profile:options.append('--use-ml-profile')
        if args.neighborhoods:options.extend(['--neighborhoods',*args.neighborhoods])
        if args.bedrooms:options.extend(['--bedrooms',*map(str,args.bedrooms)])
        options.extend(['--max-listings',str(args.max_listings)])
        result=subprocess.run([*base,'collect',*options])
        code=result.returncode
        if args.details and 'casasymas' in args.sources:
            detail_result=subprocess.run([*base,'enrich','--sources','casasymas','--limit',str(args.details),*(['--headed'] if args.headed else [])])
            code=code or detail_result.returncode
        subprocess.run([*base,'export','--out',str(output)],check=True)
        runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
        node=Path(os.environ.get('ARTIFACT_NODE',runtime/'node/bin/node'))
        if node.exists() and (root/'scripts/node_modules/@oai/artifact-tool').exists():
            subprocess.run([str(node),'scripts/export_database.mjs',str(output/'properties.json')],check=True)
        else:
            print('JSON y CSV exportados. Excel requiere el runtime @oai/artifact-tool; consultar README.')
        if code:
            print('Captura parcial o fallida: el export puede conservar avisos anteriores. Consultar runs.json y última captura.')
        return code


if __name__=='__main__':
    raise SystemExit(main())
