"""Consistent SQLite backups. Stop the worker to align queue and listing snapshots."""
import sqlite3
from datetime import datetime,timezone
from .settings import Settings


def main():
    settings=Settings.from_env()
    folder=settings.data_dir/'backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True)
    for path in (settings.database,settings.queue):
        if not path.exists():continue
        source=sqlite3.connect(f'file:{path}?mode=ro',uri=True)
        target=sqlite3.connect(folder/path.name)
        try:source.backup(target)
        finally:source.close();target.close()
    print(folder)


if __name__=='__main__':main()
