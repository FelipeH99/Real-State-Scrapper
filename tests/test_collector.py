"""Collector regression tests. Optional real Chromium tests use only localhost."""
import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from estate.collect import AccessBlocked, check_browser_access, collect, remax_snapshot
from estate.storage import Store


class AccessTests(unittest.TestCase):
    def test_login_redirect_is_not_a_layout_timeout(self):
        for path in ('/gz/account-verification?go=listing', '/login', '/captcha'):
            with self.assertRaises(AccessBlocked):
                check_browser_access('https://example.com'+path)
        check_browser_access('https://example.com/listing?title=login')


class RemaxLoadingTests(unittest.TestCase):
    def test_valid_initial_rent_results_are_not_reapplied(self):
        page=Mock()
        page.url='https://example.com/rent'
        page.content.return_value='<html>valid results</html>'
        row={'id':'1','price':30000,'currency':'UYU'}
        with patch('estate.collect.parse',return_value=[row]):
            html,url=remax_snapshot(page,'alquiler')
        self.assertEqual(html,'<html>valid results</html>')
        page.get_by_role.assert_not_called()
        page.locator.assert_not_called()

    def test_transient_invalid_cards_are_not_saved_or_immediately_reapplied(self):
        from estate.parsers import LayoutError
        page=Mock()
        page.url='https://example.com/rent'
        row={'id':'1','price':30000,'currency':'UYU'}
        with patch('estate.collect.parse',side_effect=[LayoutError('stale sales'),[row],[row]]):
            remax_snapshot(page,'alquiler')
        page.get_by_role.assert_not_called()

    def test_invalid_results_reapply_visible_operation_control(self):
        from estate.parsers import LayoutError
        page=Mock()
        page.url='https://example.com/buy'
        row={'id':'1','price':100000,'currency':'USD'}
        with patch('estate.collect.monotonic',side_effect=[0,1,9,10,11,12]), \
             patch('estate.collect.parse',side_effect=[LayoutError('wrong type'),[row],[row]]):
            remax_snapshot(page,'venta')
        page.locator.assert_called_once_with('button.toggle__button:visible')
        page.get_by_role.assert_any_call('button',name='Ver resultados',exact=True)


@unittest.skipUnless(os.environ.get('PLAYWRIGHT_TESTS')=='1',
                     'Set PLAYWRIGHT_TESTS=1 to run Chromium against localhost')
class BrowserIntegrationTests(unittest.TestCase):
    def test_remax_operation_button_ignores_duplicate_navigation_and_hidden_controls(self):
        from playwright.sync_api import sync_playwright
        from estate.parsers import LayoutError
        with sync_playwright() as pw:
            browser=pw.chromium.launch()
            try:
                page=browser.new_page()
                page.set_content('''<button>filtros (1)</button>
                  <a href="#" role="button">Comprar</a>
                  <button aria-label="Comprar" style="display:none">Comprar</button>
                  <button class="toggle__button" onclick="this.dataset.clicked='yes'"> Comprar </button>
                  <button>Ver resultados</button>''')
                row={'id':'1','price':100000,'currency':'USD'}
                with patch('estate.collect.monotonic',side_effect=[0,1,9,10,11,12]), \
                     patch('estate.collect.parse',side_effect=[LayoutError('wrong type'),[row],[row]]):
                    remax_snapshot(page,'venta')
                self.assertEqual(page.locator('button.toggle__button').get_attribute('data-clicked'),'yes')
            finally:
                browser.close()

    def test_capture_failure_diagnostics_and_partial_run(self):
        html='''<a href="/propiedad/ampliada/123"><h3>Apartamento en alquiler Alquiler $ 30.000</h3>
        <p class="data">Calle de ejemplo 123</p><p class="data">Montevideo</p>
        <p class="data">Cordón</p><p class="data">2 dormitorios</p></a>'''

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                status=403 if self.path=='/blocked' else 200
                self.send_response(status)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(('Access denied' if status==403 else html).encode())

            def log_message(self,*args):
                pass

        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                store=Store(Path(tmp)/'estate.sqlite3')
                try:
                    base=f'http://127.0.0.1:{server.server_port}'
                    config={'campiglia':dict(transport='browser',selector='a',max_pages=1,
                              urls={'alquiler':base+'/ok','venta':base+'/blocked'})}
                    with contextlib.redirect_stdout(io.StringIO()):
                        run,status=collect(store,config,['campiglia'],delay=0,output=Path(tmp)/'captures')
                    self.assertEqual(status,'partial')
                    self.assertEqual(len(store.rows()),1)
                    self.assertEqual(store.rows()[0]['price'],30000)
                    pages=store.status()[0]['pages']
                    self.assertEqual([p['status'] for p in pages],['ok','error'])
                    self.assertIn('AccessBlocked',pages[1]['error'])
                    folder=Path(tmp)/'captures'/run
                    manifest=json.loads((folder/'manifest.json').read_text())
                    self.assertEqual(len(manifest),1)
                    error=json.loads((folder/'campiglia-venta-1-error.json').read_text())
                    self.assertEqual(error['http_status'],403)
                    self.assertTrue((folder/error['html']).exists())
                    self.assertTrue((folder/error['png']).exists())
                finally:
                    store.db.close()
        finally:
            server.shutdown();server.server_close();thread.join()
