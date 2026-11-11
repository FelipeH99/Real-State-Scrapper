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
| Casas y Más | Playwright | Captura validada en alquiler y venta; ocho páginas por operación y búsquedas por barrio/dormitorios probadas |
| RE/MAX | Playwright visible (`--headed`) | Primera página validada; pruebas de paginación rechazadas porque el portal pierde los filtros |
| Mercado Libre | Playwright | Captura anónima bloqueada. Perfil local opcional; inicio de sesión manual probado, bloqueado por verificación/límite de intentos |
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

Ejecutar las fuentes de navegador disponibles, con ventana visible:

```sh
sh scripts/run.sh --sources casasymas remax --headed
```

Para incluir Mercado Libre en la comprobación manual:

```sh
sh scripts/run.sh --sources casasymas remax mercadolibre --headed
```

En la prueba actual, Mercado Libre exige una cuenta y se informa como fuente
bloqueada: no se obtienen avisos nuevos de ese portal. Esto no se corrige cambiando
selectores. El proceso continúa con las otras fuentes y termina con código `2`.
Solo usa un perfil local de Mercado Libre si lo habilitás explícitamente. No completa verificaciones automáticamente.

No se instala ninguna tarea programada. Un bloqueo de proceso impide ejecutar
dos capturas simultáneas. El código de salida `2` indica captura parcial o fallida:
la exportación puede incluir avisos de ejecuciones anteriores. Revisá siempre
la fecha de última observación y el estado de la captura. `status` y `runs.json`
incluyen el resultado de cada fuente y operación, con cantidad de avisos y error.
Los fallos generan HTML, captura PNG y diagnóstico JSON en `data/captures/<run>/`;
son archivos locales ignorados por Git.

Para probar desde una base separada y elegir la carpeta de exportación:

```sh
sh scripts/run.sh --sources casasymas remax --headed --pages 2 --db data/prueba.sqlite3 --out outputs/prueba
```

Capturar sin exportar, con navegador visible:

```sh
.venv/bin/python -m estate collect --sources casasymas mercadolibre --pages 2 --headed
```

La paginación tiene un máximo de 30 páginas por búsqueda en Casas y Más, tres
en Mercado Libre y una en Campiglia y RE/MAX. En RE/MAX se probaron la navegación
y la selección completa de filtros: las páginas siguientes devuelven resultados
inconsistentes y se mantienen deshabilitadas. No se incorporan esos avisos.

### Ampliar la muestra

```sh
sh scripts/run.sh --sources casasymas --pages 8 --max-listings 1000 --details 12
```

La captura selecciona explícitamente apartamentos en Montevideo. `--max-listings`
es un límite global de avisos nuevos en **esa ejecución**, no del tamaño acumulado
de SQLite. Si se alcanza, pueden quedar operaciones o fuentes sin recorrer.
Los IDs repetidos entre páginas y búsquedas se cuentan una sola vez por ejecución.
Cada captura conserva un `summary.json` con páginas, avisos nuevos y motivo de parada.
Una página repetida detiene la navegación sin eliminar datos anteriores.

Para distribuir la búsqueda por barrio y dormitorios:

```sh
sh scripts/run.sh --sources casasymas --neighborhoods Pocitos Cordón --bedrooms 1 2 --pages 2 --max-listings 500
```

Estos filtros de captura están habilitados para Casas y Más. Se ejecuta cada
combinación en alquiler y venta; los resultados se vuelven a filtrar por barrio
y dormitorios antes de guardarlos. Los filtros de exportación siguen disponibles
para todas las fuentes. Ampliar páginas no convierte la muestra en un censo ni en
una muestra estadísticamente representativa.

### Completar fichas individuales

```sh
.venv/bin/python -m estate enrich --sources casasymas --limit 12
.venv/bin/python -m estate enrich --sources casasymas --operation venta --limit 4
.venv/bin/python -m estate export
```

El enriquecimiento implementado corresponde a Casas y Más: completa campos
faltantes de dormitorios, baños, superficie construida, gastos comunes, barrio,
inmobiliaria y referencia externa cuando están informados. No reemplaza precios
ni datos ya conocidos del listado. Mantiene `detail_observed_at` separado de
`last_seen` para no presentar un precio antiguo como recién consultado. La opción
`--details N` del ejecutor manual realiza este paso antes de exportar, con un
máximo de 100 fichas y pausas entre visitas. Prioriza avisos sin enriquecer.
Las fichas de RE/MAX, Campiglia y Mercado Libre todavía no tienen enriquecimiento.

### Sesión manual de Mercado Libre

```sh
.venv/bin/python -m estate login
# Luego de ingresar manualmente y cerrar la ventana desde Enter en la terminal:
sh scripts/run.sh --sources mercadolibre --headed --use-ml-profile
```

El perfil dedicado está en `data/browser-profiles/mercadolibre/`, ignorado por Git.
No usa tu perfil habitual ni solicita contraseñas en la terminal. Sin
`--use-ml-profile`, la captura sigue usando un contexto anónimo. La creación de un
perfil no confirma que la sesión esté autenticada ni que el portal permita extraer.

En la prueba manual, Google rechazó el navegador y el acceso directo de Mercado
Libre alcanzó el límite de intentos. Se detuvo la prueba. Si aparece ese mensaje,
no sigas intentando: retomá manualmente cuando el portal vuelva a permitirlo.
El acceso por API con OAuth todavía requiere una aplicación autorizada y no fue
validado en este MVP.

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
| `duplicates.json` | Grupos de posibles duplicados y evidencia |
| `coverage.json` | Cantidad de avisos por fuente/operación y fichas enriquecidas |
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

Un registro representa fuente + identificador + operación. Se detectan grupos
entre portales cuando comparten una referencia externa explícita (por ejemplo,
Casasweb) o coinciden dirección con número, dormitorios, superficie, precio y
moneda. Las coincidencias de atributos son **candidatos para revisar**: dos unidades
del mismo edificio pueden compartirlos. No se fusionan ni borran avisos, ni se
presenta la cantidad de grupos como cantidad exacta de inmuebles únicos.

Los grupos se exportan en `duplicates.json` y se señalan en JSON, CSV y Excel. La ausencia de un aviso no se interpreta como una venta,
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
capturas privadas ni acceso a los portales. Para incluir la integración con un
Chromium real contra un servidor local (incluye captura, HTTP 403 y diagnósticos):

```sh
PLAYWRIGHT_TESTS=1 .venv/bin/python -m unittest discover -s tests -v
```

| Ruta | Responsabilidad |
| --- | --- |
| `estate/collect.py` | Captura y registro de fallos |
| `estate/parsers.py` | Extracción y normalización |
| `estate/legacy_parsers.py` | Compatibilidad con importaciones históricas |
| `estate/storage.py` | SQLite, filtros e historial |
| `estate/details.py` | Enriquecimiento de fichas |
| `estate/duplicates.py` | Candidatos a duplicados entre portales |
| `estate/session.py` | Perfil dedicado e inicio de sesión manual |
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
