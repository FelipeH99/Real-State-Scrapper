from http.server import BaseHTTPRequestHandler,HTTPServer

HTML='''<!doctype html><html><body>
<a href="/propiedad/ampliada/1"><h3>Apartamento en alquiler Alquiler $ 30.000</h3>
<p class="data">Calle ejemplo 123</p><p class="data">Montevideo</p><p class="data">Malvín</p><p class="data">2 dormitorios</p></a>
<a href="/propiedad/ampliada/2"><h3>Apartamento en venta Desde U$S 150.000</h3>
<p class="data">Calle ejemplo 456</p><p class="data">Montevideo</p><p class="data">Cordón</p><p class="data">1 dormitorio</p></a>
</body></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers()
        self.wfile.write(('User-agent: *\nAllow: /\n' if self.path=='/robots.txt' else HTML).encode())

HTTPServer(('0.0.0.0',8080),Handler).serve_forever()
