"""SQLite job queue. A transaction makes submission and claiming atomic."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from estate.storage import now

TERMINAL={'completed','partial','failed','cancelled'}


class Queue:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY, state TEXT NOT NULL, payload TEXT NOT NULL,
                created TEXT NOT NULL, started TEXT, finished TEXT, error TEXT,
                idempotency_key TEXT UNIQUE);
                CREATE INDEX IF NOT EXISTS jobs_state_created ON jobs(state,created);
                PRAGMA user_version=1;''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=30);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    @staticmethod
    def decode(row):
        if row is None:return None
        result=dict(row);result['request']=json.loads(result.pop('payload'))
        result.pop('idempotency_key',None)
        return result

    def submit(self,payload,key=None,limit=50):
        encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                existing=db.execute('SELECT * FROM jobs WHERE idempotency_key=?',(key,)).fetchone()
                if existing:
                    if existing['payload']!=encoded:raise ValueError('Idempotency key already used for a different request')
                    return self.decode(existing)
            active=db.execute("SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
            if active>=limit:raise OverflowError('Queue capacity reached')
            id=uuid.uuid4().hex
            db.execute('INSERT INTO jobs(id,state,payload,created,idempotency_key) VALUES(?,?,?,?,?)',
                       (id,'queued',encoded,now(),key))
            return self.decode(db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone())

    def get(self,id):
        with self.connect() as db:return self.decode(db.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone())

    def list(self,limit=50):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC,rowid DESC LIMIT ?',(limit,))]

    def claim(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created,rowid LIMIT 1").fetchone()
            if row is None:return None
            db.execute("UPDATE jobs SET state='running',started=? WHERE id=?",(now(),row['id']))
            return self.decode(db.execute('SELECT * FROM jobs WHERE id=?',(row['id'],)).fetchone())

    def finish(self,id,state,error=None):
        if state not in TERMINAL:raise ValueError('Invalid terminal state')
        with self.connect() as db:
            db.execute("UPDATE jobs SET state=?,finished=?,error=? WHERE id=? AND state='running'",(state,now(),error,id))

    def cancel(self,id):
        with self.connect() as db:
            cursor=db.execute("UPDATE jobs SET state='cancelled',finished=? WHERE id=? AND state='queued'",(now(),id))
            return cursor.rowcount==1

    def recover_interrupted(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET state='failed',finished=?,error='Worker interrupted; resubmit manually' WHERE state='running'",(now(),))
