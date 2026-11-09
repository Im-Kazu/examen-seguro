"""Servidor HTTP en la red local: los teléfonos se conectan aquí tras escanear el QR."""

from __future__ import annotations

import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
UA_APP = "ExamenSeguro"


class Estado:
    """Lo comparten el servidor y el panel."""
    examen = None             # nucleo.Examen | None
    permitir_navegador = False  # para pruebas: acepta navegadores normales


def ips_locales() -> list[str]:
    """IPs IPv4 de esta PC; la primera es la de la ruta por defecto (normalmente el Wi-Fi)."""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no envía nada, solo elige la interfaz
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith(("127.", "169.254.")):
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


class Manejador(BaseHTTPRequestHandler):
    server_version = "ExamenSeguroServidor/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silencio en consola
        pass

    # ---------- utilidades
    def _enviar(self, codigo: int, cuerpo: bytes, tipo: str):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, codigo: int, datos: dict):
        self._enviar(codigo, json.dumps(datos, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _html(self, codigo: int, texto: str):
        self._enviar(codigo, texto.encode("utf-8"), "text/html; charset=utf-8")

    def _cuerpo(self) -> dict:
        n = min(int(self.headers.get("Content-Length") or 0), 100_000)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, UnicodeDecodeError):
            return {}

    def _es_app(self) -> bool:
        return Estado.permitir_navegador or UA_APP in (self.headers.get("User-Agent") or "")

    def _aviso(self, titulo, texto, codigo=403):
        self._html(codigo, f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{titulo}</title>
<body style="font-family:system-ui;padding:32px;text-align:center;background:#0f1b3d;color:#fff">
<div style="font-size:48px">🔒</div><h2>{titulo}</h2><p style="color:#cbd5e1">{texto}</p></body>""")

    # ---------- rutas
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        x = Estado.examen
        if url.path == "/":
            return self._aviso("Examen Seguro", "Abre la app <b>Examen Seguro</b> en tu teléfono y escanea el QR del docente.", 200)
        if url.path == "/favicon.ico":
            return self._enviar(204, b"", "image/x-icon")
        if not self._es_app():
            return self._aviso("Usa la app Examen Seguro", "Este examen solo se puede abrir desde la app Examen Seguro.")
        if x is None:
            return self._aviso("No hay examen activo", "Espera a que el docente inicie el examen.", 404)
        if url.path in ("/examen", "/fin"):
            with open(os.path.join(WEB, "examen.html"), "rb") as f:
                return self._enviar(200, f.read(), "text/html; charset=utf-8")
        if url.path == "/api/examen":
            d = x.datos(q.get("t", ""))
            return self._json(200, d) if d else self._json(404, {"error": "Sesión inválida"})
        if url.path == "/api/resultado":
            e = x.estudiantes.get(q.get("t", ""))
            return self._json(200, x.resultado(e)) if e else self._json(404, {"error": "Sesión inválida"})
        self._json(404, {"error": "No encontrado"})

    def do_POST(self):
        url = urlparse(self.path)
        x = Estado.examen
        if not self._es_app():
            return self._json(403, {"error": "Este examen solo se puede abrir desde la app Examen Seguro."})
        if x is None:
            return self._json(404, {"error": "No hay un examen activo en este momento."})
        b = self._cuerpo()
        t = str(b.get("t", ""))
        if url.path == "/api/unirse":
            codigo, datos = x.unirse(str(b.get("nombre", "")), str(b.get("codigo", "")),
                                     str(b.get("dispositivo", ""))[:64], str(b.get("modelo", ""))[:80],
                                     self.client_address[0])
            return self._json(codigo, datos)
        if url.path == "/api/responder":
            codigo, datos = x.responder(t, str(b.get("pregunta", "")), b.get("valor"))
            return self._json(codigo, datos)
        if url.path == "/api/latido":
            d = x.latido(t)
            return self._json(200, d) if d else self._json(404, {"error": "Sesión inválida"})
        if url.path == "/api/entregar":
            d = x.entregar(t, "entregado")
            return self._json(200, d) if d else self._json(404, {"error": "Sesión inválida"})
        if url.path == "/api/telemetria":
            ok = x.telemetria(t, str(b.get("tipo", "info")), str(b.get("detalle", "")))
            return self._json(200 if ok else 404, {"ok": ok})
        if url.path == "/api/terminar":
            motivo = str(b.get("motivo", "Salió de la app"))[:300]
            d = x.entregar(t, "terminado", motivo)
            return self._json(200, d) if d else self._json(404, {"error": "Sesión inválida"})
        self._json(404, {"error": "No encontrado"})


def iniciar(puerto_inicial: int = 8765) -> tuple[ThreadingHTTPServer, int]:
    """Arranca el servidor en el primer puerto libre a partir de puerto_inicial."""
    for puerto in range(puerto_inicial, puerto_inicial + 20):
        try:
            srv = ThreadingHTTPServer(("0.0.0.0", puerto), Manejador)
            srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            return srv, puerto
        except OSError:
            continue
    raise OSError("No hay puertos libres entre %d y %d" % (puerto_inicial, puerto_inicial + 19))
