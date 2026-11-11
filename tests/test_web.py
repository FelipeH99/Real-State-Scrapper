import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from estate.service.api import create_app
from estate.service.settings import Settings
from estate.storage import Store, now
from estate.parsers import record


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.settings=Settings(Path(self.tmp.name),'x'*40)
        store=Store(self.settings.database)
        run=store.start()
        store.save(run,[record('campiglia',str(i),'venta',title='Apartamento '+str(i),neighborhood='Pocitos',bedrooms=2,price=100000+i,currency='USD',url='https://www.campiglia.com.uy/') for i in range(30)],now())
        store.db.close()
        self.app=create_app(self.settings)

    def tearDown(self):self.tmp.cleanup()

    def test_session_and_filtered_export(self):
        import zipfile,io
        with TestClient(self.app) as client:
            self.assertEqual(client.get('/').status_code,200)
            self.assertIn("script-src 'self'",client.get('/').headers['content-security-policy'])
            self.assertEqual(client.get('/assets/app.js').status_code,200)
            self.assertEqual(client.get('/listings').status_code,401)
            self.assertEqual(client.post('/session',json={'token':'wrong'}).status_code,401)
            response=client.post('/session',json={'token':self.settings.api_key})
            self.assertIn('HttpOnly',response.headers['set-cookie'])
            self.assertIn('SameSite=strict',response.headers['set-cookie'])
            self.assertEqual(client.post('/jobs',json={}).status_code,403)
            self.assertEqual(client.post('/jobs',json={},headers={'X-Requested-With':'EstateWeb','Origin':'https://evil.test'}).status_code,403)
            self.assertEqual(client.get('/listings/meta').json()['total'],30)
            self.assertEqual(client.get('/listings?min_price=1').status_code,422)
            query='currency=USD&min_price=100010&max_price=100020&sort=price_desc&bedrooms=2&neighborhood=Pocitos'
            result=client.get('/listings?'+query+'&limit=2').json()
            self.assertEqual(result['total'],11)
            self.assertEqual(result['items'][0]['price'],100020)
            response=client.get('/listings/export?'+query)
            self.assertEqual(response.status_code,200)
            import xml.etree.ElementTree as E
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                sheet=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
                self.assertEqual(len(sheet.findall('.//{*}row')),12)
            self.assertEqual(client.delete('/session',headers={'X-Requested-With':'EstateWeb'}).status_code,200)
            self.assertEqual(client.get('/listings').status_code,401)

    @unittest.skipUnless(os.getenv('PLAYWRIGHT_TESTS')=='1','Opt-in browser tests')
    def test_browser_workflow(self):
        import uvicorn
        from playwright.sync_api import sync_playwright,expect
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(self.app,log_level='error'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            with sync_playwright() as p:
                browser=p.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{port}')
                page.locator('#access-key').fill(self.settings.api_key);page.locator('#login-submit').click()
                expect(page.locator('#result-count')).to_have_text('30 avisos')
                expect(page.locator('#properties-body tr')).to_have_count(25)
                page.locator('#next').click();expect(page.locator('#properties-body tr')).to_have_count(5)
                page.locator('#currency').select_option('USD');page.locator('#neighborhood').select_option('Pocitos');page.locator('#bedrooms').select_option('2');page.locator('#min-price').fill('100010');page.locator('#max-price').fill('100020');page.get_by_role('button',name='Aplicar filtros').click()
                expect(page.locator('#result-count')).to_have_text('11 avisos')
                with page.expect_download() as download:page.locator('#export').click()
                self.assertTrue(Path(download.value.path()).read_bytes().startswith(b'PK'))
                page.get_by_role('button',name='Nueva captura',exact=True).first.click()
                page.locator('#capture-submit').click()
                expect(page.locator('.status-tag')).to_have_text('En cola')
                page.locator('#jobs-list').get_by_role('button',name='Cancelar').click()
                expect(page.locator('.status-tag')).to_have_text('Cancelada')
                page.reload();expect(page.locator('#app')).to_be_visible()
                self.assertEqual(page.evaluate('localStorage.length + sessionStorage.length'),0)
                page.set_viewport_size({'width':390,'height':844})
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                page.get_by_role('button',name='Nueva captura',exact=True).first.click();expect(page.locator('#capture-dialog')).to_be_visible()
                page.get_by_role('button',name='Cerrar ventana').click()
                page.locator('#logout').click();expect(page.locator('#login')).to_be_visible()
                self.assertEqual(errors,[]);browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=10);sock.close()
