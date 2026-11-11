"""Portable XLSX export for the deployed application (no Codex runtime needed)."""
import json
from pathlib import Path


def write_xlsx(folder,rows=None,scope_note=None):
    import xlsxwriter
    folder=Path(folder)
    if rows is None:rows=json.loads((folder/'properties.json').read_text())
    columns=[('source','Fuente'),('id','ID'),('operation','Operación'),('neighborhood','Barrio'),
             ('bedrooms','Dormitorios'),('bathrooms','Baños'),('built_m2','Cubiertos m²'),
             ('total_m2','Totales m²'),('currency','Moneda'),('price','Precio'),
             ('expenses_currency','Moneda GC'),('expenses','Gastos comunes'),
             ('monthly_total','Alquiler + GC'),('agency','Inmobiliaria'),('title','Título'),
             ('url','URL'),('last_seen','Última captura UTC'),('detail_observed_at','Consulta ficha UTC'),
             ('duplicate_group','Grupo duplicados'),('duplicate_confidence','Evidencia'),('notes','Observaciones')]
    path=folder/'inmuebles-montevideo.xlsx'
    with xlsxwriter.Workbook(path,{'strings_to_formulas':False,'strings_to_urls':False}) as wb:
        sheet=wb.add_worksheet('Propiedades');sheet.freeze_panes(1,3)
        num=wb.add_format({'num_format':'#,##0.00'})
        header=wb.add_format({'bold':True,'bg_color':'#183B4E','font_color':'white','text_wrap':True})
        sheet.set_row(0,30);sheet.set_column(0,len(columns)-1,18)
        sheet.set_column(13,15,45);sheet.set_column(16,17,28);sheet.set_column(20,20,65)
        sheet.write_row(0,0,[label for _,label in columns],header)
        for index,row in enumerate(rows,1):
            for col,(key,_) in enumerate(columns):
                if key=='monthly_total':
                    if (row['operation']=='alquiler' and row.get('price') is not None
                        and row.get('expenses') is not None and row.get('currency')==row.get('expenses_currency')
                        and row.get('price_qualifier')=='publicado'):
                        sheet.write_formula(index,col,f'=J{index+1}+L{index+1}',num,row['price']+row['expenses'])
                    continue
                value=row.get(key)
                if value is not None:sheet.write(index,col,value,num if isinstance(value,(int,float)) else None)
        if rows:
            sheet.add_table(0,0,len(rows),len(columns)-1,{'name':'Avisos','columns':[{'header':label} for _,label in columns],'style':'Table Style Medium 2'})
        scope=wb.add_worksheet('Alcance');scope.set_column(0,0,110)
        for i,text in enumerate([
            scope_note or 'Exportación de la base: incluye avisos anteriores si alguna fuente falló.',
            'Revisar runs.json y las fechas. Los avisos no equivalen a inmuebles únicos.',
            'Los grupos de duplicados son candidatos para revisar; no se eliminan registros.',
            'Precios originales; no se convierten monedas. Vacío no significa cero.',
            'Alquiler + GC solo suma importes informados en la misma moneda, sin precios desde.',
            'La consulta de ficha no actualiza la fecha del precio del listado.',
        ]):scope.write(i,0,text)
    return path
