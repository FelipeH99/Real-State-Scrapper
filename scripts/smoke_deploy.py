"""Docker smoke test: synthetic source -> durable job -> SQLite -> authenticated files."""
import argparse
import http.client
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8000');args=p.parse_args()
key=(Path(__file__).resolve().parents[1]/'.secrets/api_key').read_text().strip()


def request(path,body=None,auth=True,headers=None):
    hdr={'Authorization':f'Bearer {key}'} if auth else {}
    hdr.update(headers or {})
    if body is not None:hdr['Content-Type']='application/json'
    req=urllib.request.Request(args.url+path,data=json.dumps(body).encode() if body is not None else None,headers=hdr)
    with urllib.request.urlopen(req,timeout=10) as response:return response.read()

for attempt in range(60):
    try:request('/health/ready',auth=False);break
    except (urllib.error.URLError,TimeoutError,http.client.HTTPException,ConnectionError):time.sleep(1)
else:raise SystemExit('Service did not become ready')
try:request('/jobs',auth=False)
except urllib.error.HTTPError as exc:assert exc.code==401
else:raise AssertionError('Unauthenticated access was allowed')
job=json.loads(request('/jobs',{'sources':['campiglia'],'pages':1,'max_listings':10,'headed':False},headers={'Idempotency-Key':'docker-smoke'}))
for attempt in range(120):
    job=json.loads(request('/jobs/'+job['id']))
    if job['state'] not in ('queued','running'):break
    time.sleep(1)
assert job['state']=='completed',job
properties=json.loads(request(f'/jobs/{job["id"]}/files/properties.json'))
assert len(properties)==2,properties
assert {r['operation'] for r in properties}=={'venta','alquiler'}
book=request(f'/jobs/{job["id"]}/files/inmuebles-montevideo.xlsx')
assert book[:2]==b'PK'
filtered=json.loads(request('/listings?operation=alquiler&currency=UYU&max_price=35000'))
assert filtered['total']==1
print(json.dumps({'smoke':'passed','job':job['id'],'ads':len(properties),'xlsx_bytes':len(book)}))
