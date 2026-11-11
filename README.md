# Real Estate Scrapper · Montevideo

MVP de una herramienta local para recopilar avisos de apartamentos en alquiler y
venta, consultar precios por barrio y dormitorios, conservar un historial y
exportar resultados. Está implementada en Python y se usa desde la terminal.
Todavía no incluye una interfaz web.

## Funcionalidades

- Captura manual por fuente y operación, con límites de páginas y pausas.
- Normalización de precios, monedas, superficies y gastos comunes.
- Filtros por fuente, operación, barrio, dormitorios, moneda y precio máximo.
- Base SQLite con fechas de observación e historial de cambios de precio.
- Registro de errores por fuente y conservación de datos anteriores ante fallos.
- Exportación JSON y CSV; Excel mediante un generador opcional.

## Fuentes y estado del MVP

| Fuente | Integración | Estado |
| --- | --- | --- |
| Campiglia | HTTP | Captura y exportación probadas en vivo |
| Casas y Más | Playwright | Parser validado con capturas de navegador; ejecución autónoma pendiente de validar |
| RE/MAX | Playwright | Parser validado con capturas de navegador; ejecución autónoma pendiente de validar |
| Mercado Libre | Playwright | Parser validado con capturas de navegador; ejecución autónoma pendiente de validar |
| InfoCasas y Casasweb | Importación de HTML | Parsers disponibles; captura en vivo deshabilitada |

El acceso depende de cada portal y puede cambiar. Un bloqueo o desafío se registra
como fallo; el MVP no implementa resolución de CAPTCHA ni proxies. Revisá las
condiciones y autorizaciones de cada fuente antes de reutilizar su catálogo.

## Requisitos e instalación

Python 3.10 o superior. El ejecutor manual usa `fcntl`, disponible en macOS/Linux.
Chromium solo es necesario para las fuentes que utilizan Playwright.

```sh
git clone https://github.com/FelipeH99/Real-State-Scrapper.git
cd Real-State-Scrapper
python3 -m venv .venv
.venv/bin/pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
```

Para trabajar únicamente con HTTP, importaciones y exportaciones JSON/CSV,
basta instalar `requirements.txt` en el entorno virtual.

## Uso manual

Capturar Campiglia y exportar la base:

```sh
sh scripts/run.sh --sources campiglia
```

Intentar todas las fuentes habilitadas, una página por operación:

```sh
sh scripts/run.sh
```

No se instala ninguna tarea programada. Un bloqueo de proceso impide ejecutar
dos capturas simultáneas. El código de salida `2` indica captura parcial o fallida:
la exportación puede incluir avisos de ejecuciones anteriores. Revisá siempre
la fecha de última observación y el estado de la captura.

Capturar sin exportar, con navegador visible:

```sh
.venv/bin/python -m estate collect --sources casasymas mercadolibre --pages 2 --headed
```

La paginación tiene un máximo de tres páginas por búsqueda en Casas y Más y
Mercado Libre, y una en Campiglia y RE/MAX. En RE/MAX está limitada porque la
navegación puede perder los filtros; se rechazan resultados contradictorios.

### Consultar y exportar

```sh
.venv/bin/python -m estate status
.venv/bin/python -m estate changes
.venv/bin/python -m estate export --operation alquiler --neighborhood Cordón --bedrooms 1 --currency UYU --max-price 35000 --out outputs/filtrado
```

`--max-price` requiere `--currency` para evitar comparar pesos con dólares.
La tipología del MVP está limitada a apartamentos. Los filtros de barrio dependen
de que el portal informe ese dato.

La exportación predeterminada se escribe en `outputs/automated/`:

| Archivo | Contenido |
| --- | --- |
| `properties.json` | Avisos normalizados |
| `properties.csv` | Avisos para abrir en Excel u otras herramientas |
| `changes.json` | Historial de cambios de la base completa |
| `runs.json` | Estado de las ejecuciones de la base completa |
| `inmuebles-montevideo.xlsx` | Libro opcional con filtros y notas de alcance |

Los filtros de exportación se aplican a los avisos, no a `changes.json` ni a
`runs.json`. Los archivos exportados son estáticos; no se actualizan solos.

### Excel opcional

`scripts/export_database.mjs` depende de `@oai/artifact-tool`, disponible en el
runtime de Codex. Esa dependencia no se distribuye en este repositorio ni se
instala con `pip`. El ejecutor intenta usar el Node del runtime local y busca la
librería en `scripts/node_modules`; `ARTIFACT_NODE` permite indicar otro Node.

Si ese entorno no está disponible, se generan JSON y CSV y se informa que Excel
no pudo generarse. El CSV se puede abrir directamente en Excel.

### Importar capturas

```sh
.venv/bin/python -m estate import /ruta/al/manifest.json
```

El manifiesto es una lista JSON. Las rutas relativas se resuelven desde su carpeta:

```json
[
  {
    "source": "campiglia",
    "operation": "alquiler",
    "url": "https://campiglia.com.uy/inmobiliaria",
    "file": "campiglia.html",
    "observed_at": "2026-01-01T12:00:00+00:00"
  }
]
```

Usá la fecha real de captura. Las importaciones repetidas no duplican la misma
observación y una captura antigua no reemplaza los datos más recientes.

## Persistencia y calidad de datos

La base se crea en `data/estate.sqlite3` y las capturas de diagnóstico se guardan
en `data/captures/`. Las fechas se normalizan a UTC. Para usar otra base:

```sh
.venv/bin/python -m estate --db /ruta/a/otra.sqlite3 status
```

Un registro representa fuente + identificador + operación. No se deduplican
inmuebles entre portales. La ausencia de un aviso no se interpreta como una venta,
un alquiler confirmado ni una baja.

Se preservan monedas originales y precios «desde». Los campos desconocidos quedan
vacíos; no equivalen a cero. La fórmula de alquiler + gastos comunes del Excel
solo suma importes conocidos en la misma moneda y con precio publicado exacto.
Las tarjetas pueden omitir información o clasificar ubicaciones de forma imprecisa;
revisá el enlace de origen antes de comparar. No se verifican precios de cierre.

## Desarrollo

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Las pruebas usan datos sintéticos y bases temporales; no necesitan credenciales,
capturas privadas ni acceso a los portales.

| Ruta | Responsabilidad |
| --- | --- |
| `estate/collect.py` | Captura y registro de fallos |
| `estate/parsers.py` | Extracción y normalización |
| `estate/legacy_parsers.py` | Compatibilidad con importaciones históricas |
| `estate/storage.py` | SQLite, filtros e historial |
| `estate/__main__.py` | Comandos |
| `config/sources.json` | Fuentes y búsquedas habilitadas |
| `scripts/run_manual.py` | Captura y exportación con bloqueo de proceso |
| `scripts/export_database.mjs` | Generador Excel opcional |
| `tests/` | Pruebas del motor |

## Contenido del repositorio público

Se versionan código, configuración pública, pruebas y documentación del MVP.
Los datos extraídos, bases, reportes, credenciales, dependencias e investigación
local están excluidos mediante `.gitignore`. La carpeta `research/` es local y
no se publica. Ninguna rama de este repositorio público debe usarse para guardar
información privada.

`.gitignore` no elimina archivos de commits anteriores ni protege archivos
agregados con `git add -f`. Revisá el contenido preparado antes de publicar.
