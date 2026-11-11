import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=30)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, started TEXT, ended TEXT, status TEXT);
        CREATE TABLE IF NOT EXISTS pages(run_id TEXT, source TEXT, operation TEXT, url TEXT,
          status TEXT, records INTEGER, error TEXT);
        CREATE TABLE IF NOT EXISTS listings(source TEXT, id TEXT, operation TEXT, first_seen TEXT,
          last_seen TEXT, payload TEXT, PRIMARY KEY(source,id,operation));
        CREATE TABLE IF NOT EXISTS listing_details(source TEXT,id TEXT,operation TEXT,observed_at TEXT,payload TEXT,PRIMARY KEY(source,id,operation));
        CREATE TABLE IF NOT EXISTS observations(source TEXT,id TEXT,operation TEXT,observed_at TEXT,
          run_id TEXT,payload TEXT,PRIMARY KEY(source,id,operation,observed_at));
        ''')

    def start(self):
        id=uuid.uuid4().hex
        self.db.execute('INSERT INTO runs VALUES(?,?,NULL,?)',(id,now(),'running'))
        self.db.commit()
        return id

    def save(self,run,rows,observed_at):
        # UTC normalization makes lexical comparison valid across timezone offsets.
        stamp=datetime.fromisoformat(observed_at).astimezone(timezone.utc).isoformat(timespec='seconds')
        with self.db:
            for r in rows:
                payload=json.dumps(r,ensure_ascii=False,sort_keys=True)
                key=(r['source'],r['id'],r['operation'])
                self.db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?)',(*key,stamp,run,payload))
                self.db.execute('''INSERT INTO listings VALUES(?,?,?,?,?,?)
                  ON CONFLICT(source,id,operation) DO UPDATE SET
                    first_seen=MIN(first_seen,excluded.first_seen),
                    payload=CASE WHEN excluded.last_seen>=last_seen THEN excluded.payload ELSE payload END,
                    last_seen=MAX(last_seen,excluded.last_seen)''',(*key,stamp,stamp,payload))

    def page(self,run,source,operation,url,status,count=0,error=''):
        with self.db:
            self.db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?)',(run,source,operation,url,status,count,error))

    def finish(self,run):
        results=[r[0] for r in self.db.execute('SELECT status FROM pages WHERE run_id=?',(run,))]
        status='success' if results and all(x=='ok' for x in results) else 'partial' if 'ok' in results else 'failed'
        with self.db:
            self.db.execute('UPDATE runs SET ended=?,status=? WHERE id=?',(now(),status,run))
        return status

    def rows(self,source=None,operation=None,neighborhood=None,bedrooms=None,currency=None,max_price=None):
        from .parsers import fold
        if max_price is not None and not currency:
            raise ValueError('--max-price requires --currency to avoid mixing UYU and USD')
        result=[]
        for item in self.db.execute('SELECT * FROM listings ORDER BY source,operation,id'):
            r=json.loads(item['payload'])
            detail=self.db.execute('SELECT observed_at,payload FROM listing_details WHERE source=? AND id=? AND operation=?',(r['source'],r['id'],r['operation'])).fetchone()
            r['detail_observed_at']=detail['observed_at'] if detail else None
            r['external_reference']=None
            if detail:
                fields=json.loads(detail['payload'])
                if r.get('expenses') is None and fields.get('expenses') is not None:
                    r['expenses']=fields['expenses']
                    r['expenses_currency']=fields.get('expenses_currency')
                for key,value in fields.items():
                    if key in ('expenses','expenses_currency'):continue
                    if r.get(key) in (None,''):
                        r[key]=value
            if source and r['source'] != source: continue
            if operation and r['operation'] != operation: continue
            if neighborhood and fold(r['neighborhood']) != fold(neighborhood): continue
            if bedrooms is not None and r['bedrooms'] != bedrooms: continue
            if currency and r['currency'] != currency: continue
            if max_price is not None and (r['price'] is None or r['price']>max_price): continue
            r.update(first_seen=item['first_seen'],last_seen=item['last_seen'])
            result.append(r)
        return result

    def save_details(self,row,fields,observed_at):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO listing_details VALUES(?,?,?,?,?)',
                (row['source'],row['id'],row['operation'],observed_at,json.dumps(fields,ensure_ascii=False)))

    def changes(self):
        previous={};changes=[]
        for item in self.db.execute('SELECT * FROM observations ORDER BY observed_at,source,id,operation'):
            key=(item['source'],item['id'],item['operation'])
            p=json.loads(item['payload']);current=(p['price'],p['currency'],p.get('price_qualifier'))
            if key in previous and previous[key] != current:
                changes.append(dict(source=key[0],id=key[1],operation=key[2],observed_at=item['observed_at'],
                                    before=previous[key],after=current,url=p['url']))
            previous[key]=current
        return changes

    def status(self):
        runs=[dict(r) for r in self.db.execute('SELECT * FROM runs ORDER BY started DESC LIMIT 10')]
        for run in runs:
            run['pages']=[dict(r) for r in self.db.execute(
                'SELECT source,operation,url,status,records,error FROM pages WHERE run_id=? ORDER BY rowid',
                (run['id'],))]
        return runs
