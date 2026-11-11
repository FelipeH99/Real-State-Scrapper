import json
import tempfile
import unittest
from pathlib import Path

from estate.parsers import casasymas, remax, LayoutError, num, record
from estate.storage import Store


class DataQualityTests(unittest.TestCase):
    def test_decimal_measurement_not_thousands(self):
        self.assertEqual(num('56.79',decimal_dot=True),56.79)
        self.assertEqual(num('7.274 UYU'),7274)

    def test_original_currency_beats_converted_display(self):
        html='''<h1>Alquiler en Montevideo</h1><a class="prop-entrada" href="/propiedad/1" data-impression-property-id="1">
        <h2 class="titulo-prop">Apartamento</h2><p class="localidad_p"><span>Centro</span>Apartamento</p>
        <div class="precio-row"><span class="operacion">Alquiler</span>
        <span class="js-price-value" data-price-raw="26000" data-price-currency="UYU" data-price-hidden="0">U$S 635</span></div>
        <li><img title="Dormitorios">0</li></a>'''
        r=casasymas(html,'alquiler','https://www.casasymas.com.uy')[0]
        self.assertEqual((r['price'],r['currency']),(26000,'UYU'))
        self.assertIsNone(r['expenses'])

    def test_heading_does_not_override_contradictory_cards(self):
        html='''<h1>100 apartamentos en alquiler en Montevideo</h1>
        <a class="card-remax__href" href="/listings/x"><p class="card__description">VENTA TERRENO</p></a>'''
        with self.assertRaises(LayoutError):remax(html,'alquiler','https://www.remax.com.uy')

    def test_wrong_geography_is_not_silently_imported(self):
        with self.assertRaises(LayoutError):casasymas('<h1>Venta en Uruguay</h1>','venta','https://www.casasymas.com.uy')


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'test.sqlite3')
        self.row=record('test','1','alquiler',price=30000,currency='UYU',price_qualifier='publicado',url='https://example.com/1')

    def tearDown(self):
        self.store.db.close();self.tmp.cleanup()

    def test_idempotent_import_and_price_history(self):
        run=self.store.start()
        self.store.save(run,[self.row],'2026-11-11T10:00:00-03:00')
        self.store.save(run,[self.row],'2026-11-11T13:00:00+00:00')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],1)
        newer={**self.row,'price':29000}
        self.store.save(run,[newer],'2026-11-12T10:00:00-03:00')
        self.assertEqual(len(self.store.changes()),1)
        self.assertEqual(self.store.rows()[0]['price'],29000)
        self.store.save(run,[self.row],'2026-11-10T10:00:00-03:00')
        self.assertEqual(self.store.rows()[0]['price'],29000)

    def test_failed_source_preserves_previous_listings(self):
        run=self.store.start();self.store.save(run,[self.row],'2026-11-11T13:00:00+00:00')
        self.store.page(run,'test','alquiler','https://example.com','error',error='403')
        self.assertEqual(self.store.finish(run),'failed')
        self.assertEqual(len(self.store.rows()),1)

    def test_no_price_filter_across_currencies(self):
        with self.assertRaises(ValueError):self.store.rows(max_price=50000)


if __name__=='__main__':unittest.main()
