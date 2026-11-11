import tempfile
import unittest
from pathlib import Path

from estate.details import parse_casas_detail
from estate.duplicates import annotate_duplicates
from estate.parsers import record,LayoutError
from estate.storage import Store


class DuplicateTests(unittest.TestCase):
    def test_shared_external_reference_preserves_both_ads(self):
        rows=[record('casasymas','100','alquiler',url='https://example.com/a'),
              record('casasweb','CW123','alquiler',url='https://example.com/b')]
        rows[0]['external_reference']='CW123'
        groups=annotate_duplicates(rows)
        self.assertEqual(len(groups),1)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['duplicate_group'],rows[1]['duplicate_group'])
        self.assertEqual(groups[0]['confidence'],'referencia compartida')

    def test_shared_reference_different_operation_is_not_merged(self):
        rows=[dict(record('casasymas','100','alquiler'),external_reference='CW123'),record('casasweb','CW123','venta')]
        self.assertEqual(annotate_duplicates(rows),[])

    def test_similar_address_only_creates_review_candidate(self):
        fields=dict(address='Calle Ejemplo 123',bedrooms=1,built_m2=40,price=30000,currency='UYU',url='https://example.com')
        rows=[record('a','1','alquiler',**fields),record('b','2','alquiler',**fields)]
        self.assertEqual(annotate_duplicates(rows)[0]['confidence'],'candidato: revisar')
        rows[1]['address']='Calle Ejemplo'
        self.assertEqual(annotate_duplicates(rows),[])


class DetailTests(unittest.TestCase):
    def test_extract_only_supported_detail_fields(self):
        html='''<h1>Apartamento en alquiler en Centro, Montevideo</h1>
        <div class="feature-item"><div class="feature-label">Gastos comunes</div><div class="feature-value">$4.000</div></div>
        <div class="feature-item"><div class="feature-label">m²</div><div class="feature-value">40</div></div>
        <span class="agency-badge-name">Inmobiliaria de ejemplo</span>
        <div class="description-content">Sincronizada desde Casasweb.com ref: CW123</div>'''
        fields=parse_casas_detail(html,{'operation':'alquiler'})
        self.assertEqual(fields['expenses'],4000)
        self.assertEqual(fields['expenses_currency'],'UYU')
        self.assertEqual(fields['external_reference'],'CW123')
        self.assertNotIn('total_m2',fields)
        with self.assertRaises(LayoutError):parse_casas_detail(html,{'operation':'venta'})

    def test_dual_operation_detail_uses_breadcrumb_and_price_labels(self):
        html='''<div class="property-header"><h1>Venta Alquiler Rambla</h1>
        <div class="property-bread-links">Venta Apartamento Montevideo Carrasco</div>
        <div class="price-label">Venta</div><div class="price-label">Alquiler</div></div>
        <span class="agency-badge-name">Agencia de ejemplo</span>'''
        self.assertEqual(parse_casas_detail(html,{'operation':'alquiler'})['agency'],'Agencia de ejemplo')

    def test_enrichment_does_not_refresh_list_price_or_override_known_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'test.sqlite3')
            try:
                row=record('casasymas','1','alquiler',price=30000,currency='UYU',bedrooms=1)
                run=store.start();store.save(run,[row],'2026-01-01T12:00:00+00:00')
                store.save_details(row,{'bedrooms':2,'agency':'Ejemplo','expenses':4000},'2026-02-01T12:00:00+00:00')
                result=store.rows()[0]
                self.assertEqual(result['last_seen'],'2026-01-01T12:00:00+00:00')
                self.assertEqual(result['bedrooms'],1)
                self.assertEqual(result['agency'],'Ejemplo')
                self.assertEqual(result['detail_observed_at'],'2026-02-01T12:00:00+00:00')
                self.assertEqual(store.changes(),[])
            finally:store.db.close()
