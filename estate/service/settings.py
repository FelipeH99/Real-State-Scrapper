import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_key: str = ''
    job_timeout: int = 3600
    max_queue: int = 50

    @classmethod
    def from_env(cls, require_key=False):
        root=Path(os.environ.get('ESTATE_DATA_DIR','data')).resolve()
        key_file=os.environ.get('ESTATE_API_KEY_FILE')
        key=Path(key_file).read_text().strip() if key_file else os.environ.get('ESTATE_API_KEY','')
        if require_key and len(key)<32:
            raise RuntimeError('Configure ESTATE_API_KEY_FILE or ESTATE_API_KEY with at least 32 characters')
        timeout=int(os.environ.get('ESTATE_JOB_TIMEOUT','3600'))
        if timeout<30:raise ValueError('ESTATE_JOB_TIMEOUT must be at least 30 seconds')
        return cls(root,key,timeout)

    @property
    def database(self):return self.data_dir/'estate.sqlite3'

    @property
    def queue(self):return self.data_dir/'jobs.sqlite3'

    @property
    def jobs_dir(self):return self.data_dir/'jobs'
