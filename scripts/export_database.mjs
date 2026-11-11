import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const input=path.resolve(process.argv[2]??'outputs/automated/properties.json');
const out=path.dirname(input);
const rows=JSON.parse(await fs.readFile(input,'utf8'));
const wb=Workbook.create();
const s=wb.worksheets.add('Propiedades');
const scope=wb.worksheets.add('Fuentes y alcance');
const columns=[['source','Fuente'],['id','ID aviso'],['operation','Operación'],['neighborhood','Barrio según fuente'],['bedrooms','Dormitorios'],['bathrooms','Baños'],['built_m2','Cubiertos m²'],['total_m2','Totales m²'],['currency','Moneda precio'],['price','Precio publicado'],['price_qualifier','Tipo de precio'],['expenses_currency','Moneda GC'],['expenses','GC mensual'],[null,'Alquiler + GC¹'],['agency','Anunciante'],['title','Título'],['notes','Observaciones'],['last_seen','Última captura UTC'],['url','URL del aviso'],['duplicate_group','Grupo de posibles duplicados'],['duplicate_confidence','Evidencia duplicado'],['external_reference','Referencia externa'],['detail_observed_at','Consulta de ficha UTC']];
const end=rows.length+6;
s.showGridLines=false;
s.getRange(`A1:W${Math.max(end,7)}`).format.font={name:'Arial',size:10,color:'#173546'};
s.mergeCells('A1:W1');s.getRange('A1').values=[['Monitor inmobiliario · Montevideo']];
s.getRange('A1:W1').format={fill:'#183B4E',font:{color:'#FFFFFF',size:16,bold:true},rowHeight:34};
const notes=[`${rows.length} avisos de ${new Set(rows.map(r=>r.source)).size} fuentes · Muestra acotada; no representa todo el mercado ni inmuebles únicos.`,
 'Filtrá desde los encabezados. Cada registro conserva fuente, identificador, moneda original y última captura.',
 '¹ Solo suma alquiler + GC cuando ambos están informados, en igual moneda y el precio no es «desde». Vacío no significa cero.',
 'Duplicados: candidatos para revisar; no se eliminan avisos. Consulta de ficha y captura del precio tienen fechas separadas.'];
notes.forEach((n,i)=>{s.mergeCells(`A${i+2}:S${i+2}`);s.getRange(`A${i+2}`).values=[[n]];});
s.getRange('A2:W5').format.rowHeight=22;
s.getRange('A6:W6').values=[columns.map(x=>x[1])];
if(rows.length){
 s.getRange(`A7:W${end}`).values=rows.map(r=>columns.map(([k])=>(k==='last_seen'||k==='detail_observed_at')?(r[k]?Date.parse(r[k])/86400000+25569:null):k?r[k]??null:null));
 for(let i=0;i<rows.length;i++){let n=i+7;s.getRange(`N${n}`).formulas=[[`=IF(AND(C${n}="alquiler",ISNUMBER(J${n}),ISNUMBER(M${n}),I${n}<>"",I${n}=L${n},K${n}="publicado"),J${n}+M${n},"")`]];}
 const table=s.tables.add(`A6:W${end}`,true,'Avisos');table.showFilterButton=true;
 s.getRange(`A7:W${end}`).format.rowHeight=52;
 s.getRange(`O7:Q${end}`).format.wrapText=true;
 s.getRange(`S7:V${end}`).format.wrapText=true;
 s.getRange(`E7:F${end}`).setNumberFormat('0');
 s.getRange(`G7:H${end}`).setNumberFormat('#,##0.00');
 s.getRange(`J7:J${end}`).setNumberFormat('#,##0');
 s.getRange(`M7:N${end}`).setNumberFormat('#,##0');
 s.getRange(`R7:R${end}`).setNumberFormat('dd/mm/yyyy hh:mm');
 s.getRange(`W7:W${end}`).setNumberFormat('dd/mm/yyyy hh:mm');
}
s.getRange('A6:W6').format={fill:'#24566A',font:{color:'#FFFFFF',bold:true},rowHeight:32,wrapText:true};
[17,26,13,23,13,10,16,16,16,20,17,16,17,20,30,70,76,25,65,29,26,22,26].forEach((w,i)=>s.getRangeByIndexes(0,i,Math.max(end,7),1).format.columnWidth=w);
s.getRange(`A1:W${end}`).format.verticalAlignment='center';
s.freezePanes.freezeRows(6);s.freezePanes.freezeColumns(2);

scope.showGridLines=false;
scope.getRange('A1:F20').format.font={name:'Arial',size:10,color:'#173546'};
scope.mergeCells('A1:F1');scope.getRange('A1').values=[['Fuentes, pruebas y limitaciones']];
scope.getRange('A1:F1').format={fill:'#183B4E',font:{color:'#FFFFFF',bold:true,size:16},rowHeight:34};
scope.getRange('A3:F3').values=[['Fuente','Alquileres','Ventas','Integración','Limitación','Página de referencia']];
const names=['campiglia','casasymas','remax','mercadolibre','infocasas','casasweb'];
const methods=['HTTP','Playwright','Playwright visible','Playwright / importación','Importación de HTML','Importación de HTML'];
const limits=['Precios de venta «desde». Faltan datos de ficha.','Moneda original extraída del elemento de precio; revisar ubicaciones.','Validar antes de reaplicar filtros. Usar navegador visible. Paginación desactivada.','Captura anónima bloqueada en la prueba autónoma. Revisar fecha del aviso y runs.json.','No se incluyó en el recolector en vivo. Revisar condiciones de reutilización.','No se incluyó en el recolector en vivo: condiciones prohíben extracción automatizada.'];
const urls=['https://campiglia.com.uy/inmobiliaria','https://www.casasymas.com.uy/propiedades/alquiler/montevideo','https://www.remax.com.uy/apartamentos-en-alquiler-en-montevideo','https://listado.mercadolibre.com.uy/inmuebles/apartamentos/alquiler/montevideo/apartamentos-alquiler_NoIndex_True','https://www.infocasas.com.uy/informacion','https://casasweb.com/condiciones.aspx'];
scope.getRange('A4:F9').values=names.map((n,i)=>[n,rows.filter(r=>r.source===n&&r.operation==='alquiler').length,rows.filter(r=>r.source===n&&r.operation==='venta').length,methods[i],limits[i],urls[i]]);
scope.getRange('A3:F3').format={fill:'#24566A',font:{color:'#FFFFFF',bold:true},rowHeight:30};
scope.getRange('A4:F9').format.wrapText=true;scope.getRange('A4:F9').format.rowHeight=64;
const scopeNotes=[
 'Un registro = fuente + ID + operación. Los grupos de duplicados son evidencia para revisión; no equivalen a inmuebles únicos.',
 'Los precios son de oferta. No se convierten monedas ni se concluye que un aviso desaparecido se vendió o alquiló.',
 'Las fuentes pueden mostrar ubicaciones o tipologías inconsistentes; conservar el enlace y revisar antes de comparar.',
 'Consultar runs.json para conocer el estado por fuente y operación. Un fallo conserva avisos anteriores: revisar última captura.',
 'Solo ejecución manual. La base conserva observaciones y fallos. El Excel es una exportación estática y no se actualiza solo.'
];
scopeNotes.forEach((n,i)=>{scope.mergeCells(`A${i+12}:F${i+12}`);scope.getRange(`A${i+12}`).values=[[n]];});
scope.getRange('A12:F16').format.rowHeight=30;
[20,14,14,30,68,70].forEach((w,i)=>scope.getRangeByIndexes(0,i,20,1).format.columnWidth=w);
scope.getRange('A1:F20').format.verticalAlignment='center';
const detailRow=rows.findIndex(r=>r.detail_observed_at)+7;
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Fuentes y alcance!A3:C9',tableMaxRows:7,tableMaxCols:3,maxChars:1200})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:20},maxChars:1000})).ndjson);
for(const [name,range,file] of [['Propiedades','A6:N11','preview-records'],['Fuentes y alcance','A1:F16','preview-sources'],['Propiedades',`T${Math.max(6,detailRow)}:W${Math.max(12,detailRow+5)}`,'preview-enrichment']]){
 const image=await wb.render({sheetName:name,range,scale:1,format:'png'});
 await fs.writeFile(path.join(out,file+'.png'),new Uint8Array(await image.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(path.join(out,'inmuebles-montevideo.xlsx'));
console.log('Workbook exported');
