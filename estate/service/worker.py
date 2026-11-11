"""One durable worker per data volume; crashes never trigger automatic re-scraping."""
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from estate.storage import Store
from .export import write_xlsx
from .queue import Queue
from .settings import Settings

ROOT=Path(__file__).resolve().parents[2]
STOP=False


def log(event,**fields):print(json.dumps(dict(event=event,**fields)),flush=True)


def heartbeat(settings):
    (settings.data_dir/'worker.heartbeat').touch()


def run_stage(command,settings,logfile,deadline):
    env={**os.environ,'ESTATE_DATA_DIR':str(settings.data_dir),'PYTHONUNBUFFERED':'1'}
    with logfile.open('a') as stream:
        process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while process.poll() is None:
                heartbeat(settings)
                if STOP or time.monotonic()>deadline:
                    raise TimeoutError('Worker stopping' if STOP else 'Job exceeded time limit')
                time.sleep(0.25)
            return process.returncode
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()


def execute_job(settings,queue,job):
    folder=settings.jobs_dir/job['id'];folder.mkdir(parents=True,exist_ok=True)
    output=folder/'output';payload=job['request']
    deadline=time.monotonic()+settings.job_timeout
    command=[sys.executable,'-m','estate','--db',str(settings.database)]
    options=['--sources',*payload['sources'],'--pages',str(payload['pages']),
             '--max-listings',str(payload['max_listings']),'--delay',str(payload['delay'])]
    if payload['headed']:options.append('--headed')
    if payload['neighborhoods']:options.extend(['--neighborhoods',*payload['neighborhoods']])
    if payload['bedrooms']:options.extend(['--bedrooms',*map(str,payload['bedrooms'])])
    def stage(args):return run_stage([*command,*args],settings,folder/'worker.log',deadline)
    log('job_started',job_id=job['id'])
    try:
        code=stage(['collect',*options])
        if code not in (0,2):raise RuntimeError(f'Collector exited {code}; inspect worker.log')
        store=Store(settings.database)
        try:collection=store.status()[0]
        finally:store.db.close()
        detail_code=0
        if code==0 or collection['status']=='partial':
            if payload['details'] and 'casasymas' in payload['sources']:
                detail_code=stage(['enrich','--sources','casasymas','--limit',str(payload['details']),
                                   *(['--headed'] if payload['headed'] else [])])
        if stage(['export','--out',str(output)])!=0:raise RuntimeError('Export failed; inspect worker.log')
        heartbeat(settings);write_xlsx(output)
        state='failed' if collection['status']=='failed' else 'partial' if code or detail_code else 'completed'
        error=None if state=='completed' else 'Some collection/enrichment steps failed; inspect runs.json and worker.log'
        queue.finish(job['id'],state,error)
        log('job_finished',job_id=job['id'],state=state,collection_run=collection['id'])
    except Exception as exc:
        queue.finish(job['id'],'failed',str(exc))
        log('job_failed',job_id=job['id'],error=str(exc))


def main():
    global STOP
    settings=Settings.from_env();settings.data_dir.mkdir(parents=True,exist_ok=True)
    queue=Queue(settings.queue)
    def stop(*_):
        global STOP
        STOP=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    with (settings.data_dir/'worker.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Only one worker per data volume is supported')
        queue.recover_interrupted()
        store=Store(settings.database)
        with store.db:
            store.db.execute("UPDATE runs SET status='failed',ended=datetime('now') WHERE status='running'")
        store.db.close()
        log('worker_ready')
        try:
            while not STOP:
                heartbeat(settings)
                job=queue.claim()
                if job:execute_job(settings,queue,job)
                else:time.sleep(1)
        finally:
            (settings.data_dir/'worker.heartbeat').unlink(missing_ok=True)
            log('worker_stopped')


if __name__=='__main__':main()
