"""Restart test for a disposable Compose project; never use against production."""
import argparse
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--project',default='estate-smoke');p.add_argument('--url',default='http://127.0.0.1:8000');args=p.parse_args()
if args.project not in ('estate-smoke','estate-ci'):raise SystemExit('Only disposable test projects are allowed')
command=['docker','compose','-p',args.project,'-f','compose.yaml','-f','compose.smoke.yaml']
key=(Path(__file__).resolve().parents[1]/'.secrets/api_key').read_text().strip()
def req(path,body=None):
    request=urllib.request.Request(args.url+path,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(request,timeout=10) as r:return json.load(r)
subprocess.run([*command,'stop','worker'],check=True)
try:
    job=req('/jobs',{'sources':['campiglia'],'max_listings':10,'headed':False})
    assert job['state']=='queued'
    subprocess.run([*command,'restart','api'],check=True)
    for attempt in range(30):
        try:
            state=req('/jobs/'+job['id']);break
        except Exception:
            if attempt==29:raise
            time.sleep(1)
    assert state['state']=='queued'
finally:subprocess.run([*command,'start','worker'],check=True)
for _ in range(120):
    state=req('/jobs/'+job['id'])
    if state['state'] not in ('queued','running'):break
    time.sleep(1)
assert state['state']=='completed',state
print(json.dumps({'restart_test':'passed','job':job['id']}))
