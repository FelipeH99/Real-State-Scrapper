"""Authenticated control plane; collection happens only in the worker."""
import secrets
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator

from estate.storage import Store
from .queue import Queue
from .settings import Settings

FILES={'properties.json','properties.csv','inmuebles-montevideo.xlsx','coverage.json','duplicates.json','runs.json','changes.json'}
Source=Literal['campiglia','casasymas','remax']


class CaptureRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    sources: list[Source]=Field(default_factory=lambda:['casasymas'],min_length=1,max_length=3)
    pages: int=Field(default=1,ge=1,le=30)
    max_listings: int=Field(default=1000,ge=1,le=5000)
    details: int=Field(default=0,ge=0,le=100)
    delay: float=Field(default=3,ge=3,le=60)
    headed: bool=True
    neighborhoods: list[str]|None=Field(default=None,min_length=1,max_length=5)
    bedrooms: list[int]|None=Field(default=None,min_length=1,max_length=5)

    @model_validator(mode='after')
    def validate_filters(self):
        if len(set(self.sources))!=len(self.sources):raise ValueError('Duplicate sources')
        if (self.neighborhoods or self.bedrooms) and self.sources!=['casasymas']:
            raise ValueError('Capture partitions require sources=[casasymas]')
        if self.neighborhoods and any(not n.strip() or len(n)>80 for n in self.neighborhoods):
            raise ValueError('Invalid neighborhood')
        if self.bedrooms and any(n<0 or n>8 for n in self.bedrooms):raise ValueError('Bedrooms must be 0..8')
        return self


def create_app(settings=None):
    settings=settings or Settings.from_env(require_key=True)
    if len(settings.api_key)<32:raise RuntimeError('API key must have at least 32 characters')
    queue=Queue(settings.queue)

    @asynccontextmanager
    async def lifespan(app):
        store=Store(settings.database);store.db.close()
        yield

    app=FastAPI(title='Montevideo Real Estate Collector',version='1.0.0',lifespan=lifespan,
                description='Manual captures, durable jobs and exports. Single-host deployment.')
    bearer=HTTPBearer(auto_error=False)

    def authorize(credentials:HTTPAuthorizationCredentials|None=Depends(bearer)):
        if credentials is None or not secrets.compare_digest(credentials.credentials,settings.api_key):
            raise HTTPException(401,'Invalid API token',headers={'WWW-Authenticate':'Bearer'})

    auth=[Depends(authorize)]

    @app.get('/health/live',include_in_schema=False)
    def live():return {'status':'ok'}

    @app.get('/health/ready',include_in_schema=False)
    def ready():
        try:
            with queue.connect() as db:db.execute('SELECT 1 FROM jobs LIMIT 1')
            heartbeat=settings.data_dir/'worker.heartbeat'
            if time.time()-heartbeat.stat().st_mtime>30:raise RuntimeError()
        except Exception:raise HTTPException(503,'Worker or database unavailable')
        return {'status':'ready'}

    @app.get('/sources',dependencies=auth)
    def sources():
        return [{'source':'campiglia','max_pages':1,'status':'available'},
                {'source':'casasymas','max_pages':30,'status':'available'},
                {'source':'remax','max_pages':1,'status':'requires headed browser; remote access may differ'},
                {'source':'mercadolibre','max_pages':0,'status':'manual local login unresolved; not enabled in service'}]

    @app.post('/jobs',status_code=202,dependencies=auth)
    def submit(body:CaptureRequest,idempotency_key:str|None=Header(default=None,max_length=128)):
        try:return queue.submit(body.model_dump(),idempotency_key,settings.max_queue)
        except ValueError as exc:raise HTTPException(409,str(exc))
        except OverflowError as exc:raise HTTPException(429,str(exc))

    @app.get('/jobs',dependencies=auth)
    def jobs(limit:int=Query(50,ge=1,le=100)):return queue.list(limit)

    @app.get('/jobs/{id}',dependencies=auth)
    def job(id:str):
        result=queue.get(id)
        if not result:raise HTTPException(404,'Job not found')
        return result

    @app.post('/jobs/{id}/cancel',dependencies=auth)
    def cancel(id:str):
        if not queue.get(id):raise HTTPException(404,'Job not found')
        if not queue.cancel(id):raise HTTPException(409,'Only queued jobs can be cancelled')
        return queue.get(id)

    @app.get('/jobs/{id}/files/{filename}',dependencies=auth)
    def download(id:str,filename:str):
        job=queue.get(id)
        if not job:raise HTTPException(404,'Job not found')
        if job['state'] not in ('completed','partial'):raise HTTPException(409,'Exports are not ready')
        if filename not in FILES:raise HTTPException(404,'File not found')
        path=settings.jobs_dir/job['id']/'output'/filename
        if not path.is_file():raise HTTPException(404,'File not found')
        return FileResponse(path,filename=filename)

    @app.get('/listings',dependencies=auth)
    def listings(source:Source|None=None,operation:Literal['alquiler','venta']|None=None,
                 neighborhood:str|None=Query(None,max_length=80),bedrooms:int|None=Query(None,ge=0,le=8),
                 currency:Literal['UYU','USD']|None=None,max_price:float|None=Query(None,ge=0),
                 limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0)):
        store=Store(settings.database)
        try:rows=store.rows(source,operation,neighborhood,bedrooms,currency,max_price)
        except ValueError as exc:raise HTTPException(422,str(exc))
        finally:store.db.close()
        return {'total':len(rows),'offset':offset,'limit':limit,'items':rows[offset:offset+limit]}

    return app
