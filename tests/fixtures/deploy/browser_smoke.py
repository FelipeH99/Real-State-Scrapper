"""Run real headed Chromium and the collector inside the deployed worker image."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,'/app')
from estate.collect import collect
from estate.storage import Store

with tempfile.TemporaryDirectory() as tmp:
    store=Store(Path(tmp)/'browser.sqlite3')
    try:
        config={'campiglia':{'transport':'browser','selector':'a','max_pages':1,
                            'urls':{'alquiler':'http://fixture:8080/listings','venta':'http://fixture:8080/listings'}}}
        run,status=collect(store,config,['campiglia'],headed=True,output=Path(tmp)/'captures')
        assert status=='success',store.status()
        assert len(store.rows())==2
        print('Container Chromium capture passed: 2 synthetic ads.')
    finally:store.db.close()
