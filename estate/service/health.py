import os
import sys
import time
import urllib.request
from pathlib import Path

if sys.argv[1]=='worker':
    p=Path(os.environ.get('ESTATE_DATA_DIR','data'))/'worker.heartbeat'
    raise SystemExit(0 if p.exists() and time.time()-p.stat().st_mtime<30 else 1)
with urllib.request.urlopen('http://127.0.0.1:8000/health/live',timeout=3) as response:
    raise SystemExit(0 if response.status==200 else 1)
