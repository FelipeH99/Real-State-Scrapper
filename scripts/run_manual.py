"""One manual collection/export cycle, with a process lock and honest exit status."""
import fcntl
import os
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
os.chdir(root)
(root/'data').mkdir(exist_ok=True)
with (root/'data/run.lock').open('w') as lock:
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Ya hay una captura en ejecución.')
    args=sys.argv[1:] or ['--sources','campiglia','casasymas','remax','mercadolibre','--pages','1']
    result=subprocess.run([sys.executable,'-m','estate','collect',*args])
    subprocess.run([sys.executable,'-m','estate','export'],check=True)
    runtime=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
    node=Path(os.environ.get('ARTIFACT_NODE',runtime/'node/bin/node'))
    if node.exists() and (root/'scripts/node_modules/@oai/artifact-tool').exists():
        subprocess.run([str(node),'scripts/export_database.mjs','outputs/automated/properties.json'],check=True)
    else:
        print('JSON y CSV exportados. Excel requiere el runtime @oai/artifact-tool; consultar README.')
    if result.returncode:
        print('Captura parcial o fallida: el export puede conservar avisos anteriores. Consultar estado y última captura.')
    raise SystemExit(result.returncode)
