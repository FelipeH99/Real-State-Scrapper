"""Explicit, local browser profile for a user-assisted Mercado Libre login."""
from pathlib import Path

PROFILE=Path(__file__).resolve().parents[1]/'data/browser-profiles/mercadolibre'


def login(url):
    from playwright.sync_api import sync_playwright
    PROFILE.mkdir(parents=True,exist_ok=True,mode=0o700)
    PROFILE.chmod(0o700)
    with sync_playwright() as pw:
        context=pw.chromium.launch_persistent_context(str(PROFILE),headless=False,locale='es-UY')
        try:
            page=context.pages[0] if context.pages else context.new_page()
            page.goto(url,wait_until='domcontentloaded',timeout=45000)
            print('Ingresá manualmente en la ventana de Chromium. No compartas claves ni códigos en el chat.',flush=True)
            input('Cuando puedas ver el listado, presioná Enter aquí para guardar y cerrar la sesión: ')
            print('Perfil local guardado. La captura posterior verificará si el portal permite leer avisos.')
        finally:
            context.close()
