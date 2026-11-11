import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from estate.service.api import create_app
from estate.service.queue import Queue
from estate.service.settings import Settings
from estate.service.export import write_xlsx
from estate.service.worker import execute_job
from estate.parsers import record


class QueueTests(unittest.TestCase):
    def test_atomic_claim_idempotency_capacity_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'jobs.sqlite3';queue=Queue(path)
            first=queue.submit({'sources':['campiglia']},'same',limit=1)
            self.assertEqual(queue.submit({'sources':['campiglia']},'same',limit=1)['id'],first['id'])
            with self.assertRaises(ValueError):queue.submit({'sources':['remax']},'same')
            with self.assertRaises(OverflowError):queue.submit({},limit=1)
            with ThreadPoolExecutor(max_workers=4) as pool:
                claims=list(pool.map(lambda _:Queue(path).claim(),range(4)))
            self.assertEqual(sum(item is not None for item in claims),1)
            queue.submit({'sources':['remax']})
            Queue(path).recover_interrupted()
            self.assertEqual(queue.get(first['id'])['state'],'failed')
            self.assertEqual(sum(j['state']=='queued' for j in queue.list()),1)


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.settings=Settings(self.root,'a'*40)
        self.client=TestClient(create_app(self.settings));self.client.__enter__()
        self.auth={'Authorization':'Bearer '+'a'*40}

    def tearDown(self):
        self.client.__exit__(None,None,None);self.tmp.cleanup()

    def test_auth_validation_and_idempotency(self):
        self.assertEqual(self.client.get('/health/live').status_code,200)
        self.assertEqual(self.client.get('/health/ready').status_code,503)
        (self.root/'worker.heartbeat').touch()
        self.assertEqual(self.client.get('/health/ready').status_code,200)
        self.assertEqual(self.client.get('/jobs').status_code,401)
        self.assertEqual(self.client.post('/jobs',headers=self.auth,json={'sources':['mercadolibre']}).status_code,422)
        self.assertEqual(self.client.post('/jobs',headers=self.auth,json={'sources':['remax'],'neighborhoods':['Pocitos']}).status_code,422)
        self.assertEqual(self.client.post('/jobs',headers=self.auth,json={'command':'rm -rf /'}).status_code,422)
        headers={**self.auth,'Idempotency-Key':'retry'}
        a=self.client.post('/jobs',headers=headers,json={'sources':['campiglia']})
        b=self.client.post('/jobs',headers=headers,json={'sources':['campiglia']})
        self.assertEqual(a.status_code,202);self.assertEqual(a.json()['id'],b.json()['id'])
        self.assertEqual(self.client.post('/jobs',headers=headers,json={'sources':['remax']}).status_code,409)
        id=a.json()['id']
        self.assertEqual(self.client.post(f'/jobs/{id}/cancel',headers=self.auth).status_code,200)
        self.assertEqual(self.client.get(f'/jobs/{id}/files/worker.log',headers=self.auth).status_code,409)
        self.assertEqual(self.client.get('/listings?max_price=100',headers=self.auth).status_code,422)

    def test_file_allowlist_and_successful_download(self):
        q=Queue(self.settings.queue);job=q.submit({});q.claim();q.finish(job['id'],'completed')
        folder=self.settings.jobs_dir/job['id']/'output';folder.mkdir(parents=True)
        (folder/'properties.json').write_text('[]')
        base=f'/jobs/{job["id"]}/files/'
        self.assertEqual(self.client.get(base+'properties.json',headers=self.auth).status_code,200)
        self.assertEqual(self.client.get(base+'worker.log',headers=self.auth).status_code,404)
        self.assertEqual(self.client.get(base+'properties.json').status_code,401)


class ExportTests(unittest.TestCase):
    def test_portable_xlsx_keeps_untrusted_strings_as_text(self):
        import zipfile
        import xml.etree.ElementTree as E
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            rows=[record('test','1','alquiler',title='=HYPERLINK("https://example.com")',price=30000,
                         currency='UYU',expenses=4000,expenses_currency='UYU',price_qualifier='publicado')]
            (p/'properties.json').write_text(json.dumps(rows))
            book=write_xlsx(p)
            with zipfile.ZipFile(book) as z:
                s=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
                ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                self.assertIsNone(s.find('.//s:c[@r="O2"]/s:f',ns))
                self.assertEqual(s.find('.//s:c[@r="M2"]/s:v',ns).text,'34000')


class WorkerTests(unittest.TestCase):
    def test_timeout_is_recorded_and_job_is_not_requeued(self):
        from estate.service.api import CaptureRequest
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings(Path(tmp));q=Queue(settings.queue)
            q.submit(CaptureRequest().model_dump());job=q.claim()
            with patch('estate.service.worker.run_stage',side_effect=TimeoutError('limit exceeded')):
                execute_job(settings,q,job)
            self.assertEqual(q.get(job['id'])['state'],'failed')
            self.assertIsNone(q.claim())
