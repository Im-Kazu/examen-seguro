"""Núcleo del servidor de exámenes: bancos de preguntas, sesión de examen,
calificación y guardado de resultados (Excel + TXT)."""

from __future__ import annotations

import csv
import datetime as dt
import os
import random
import re
import secrets
import threading
import time
import unicodedata
from dataclasses import dataclass, field

LETRAS = "ABCDEFGHIJ"


# ----------------------------------------------------------------- utilidades

def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y con espacios simples (para comparar)."""
    t = unicodedata.normalize("NFD", str(texto or ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip().lower()


def ahora() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def fecha_hora(ts: float | None) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""


# ----------------------------------------------------------------- preguntas

@dataclass
class Pregunta:
    id: str
    texto: str
    tipo: str                      # opcion | multiple | vf | abierta
    opciones: list[tuple[str, str]]  # [(id, texto)]
    correctas: list[str]           # ids de opción, o textos aceptados (abierta)
    puntos: float = 1.0
    banco: str = ""

    def publica(self, orden_opciones: list[str] | None = None) -> dict:
        """Versión que se envía al estudiante: SIN respuestas correctas."""
        ops = dict(self.opciones)
        orden = orden_opciones or [o for o, _ in self.opciones]
        return {
            "id": self.id,
            "texto": self.texto,
            "tipo": self.tipo,
            "puntos": self.puntos,
            "opciones": [{"id": o, "texto": ops[o]} for o in orden if o in ops],
        }

    def texto_respuesta(self, valor) -> str:
        if self.tipo == "abierta":
            return str(valor or "")
        ops = dict(self.opciones)
        ids = valor if isinstance(valor, list) else ([valor] if valor else [])
        return "; ".join(f"{i}) {ops.get(i, '?')}" for i in ids)

    def texto_correcta(self) -> str:
        if self.tipo == "abierta":
            return " | ".join(self.correctas) if self.correctas else "(revisión manual)"
        ops = dict(self.opciones)
        return "; ".join(f"{i}) {ops.get(i, '?')}" for i in self.correctas)

    def calificar(self, valor) -> float | None:
        """Puntos obtenidos; None = requiere revisión manual."""
        if self.tipo == "abierta":
            if not self.correctas:
                return None if str(valor or "").strip() else 0.0
            ok = normalizar(valor) in {normalizar(c) for c in self.correctas}
            return self.puntos if ok else 0.0
        ids = valor if isinstance(valor, list) else ([valor] if valor else [])
        return self.puntos if set(ids) == set(self.correctas) and ids else 0.0


def _tipo(tipo_txt: str, opciones, correctas_txt: str) -> str:
    t = normalizar(tipo_txt)
    if t in ("vf", "v/f", "verdadero/falso", "verdadero falso", "verdadero o falso", "tf"):
        return "vf"
    if t.startswith("abiert") or t in ("corta", "texto", "respuesta corta", "desarrollo"):
        return "abierta"
    if not opciones:
        c = normalizar(correctas_txt)
        return "vf" if c in ("v", "f", "verdadero", "falso", "true", "false") else "abierta"
    letras = [x for x in re.split(r"[,;\s/]+", correctas_txt.strip().upper()) if x]
    return "multiple" if len(letras) > 1 or t.startswith("multi") else "opcion"


def _armar(n: int, banco: str, texto: str, tipo_txt: str, opciones: list[tuple[str, str]],
           correcta_txt: str, puntos) -> Pregunta | None:
    texto = str(texto or "").strip()
    if not texto:
        return None
    correcta_txt = str(correcta_txt or "").strip()
    tipo = _tipo(tipo_txt, opciones, correcta_txt)
    try:
        pts = float(str(puntos).replace(",", ".")) if str(puntos or "").strip() else 1.0
    except ValueError:
        pts = 1.0
    if tipo == "vf":
        opciones = [("V", "Verdadero"), ("F", "Falso")]
        c = normalizar(correcta_txt)
        correctas = ["V"] if c in ("v", "verdadero", "true", "1", "si", "cierto") else ["F"]
    elif tipo == "abierta":
        opciones = []
        correctas = [c.strip() for c in correcta_txt.split("|") if c.strip()]
    else:
        validas = {o for o, _ in opciones}
        correctas = [x for x in re.split(r"[,;\s/]+", correcta_txt.upper()) if x in validas]
        if not correctas:
            raise ValueError(f"Pregunta {n} («{texto[:40]}…»): la respuesta correcta «{correcta_txt}» "
                             f"no coincide con ninguna opción ({', '.join(sorted(validas))}).")
    return Pregunta(f"{banco[:12]}-{n}", texto, tipo, opciones, correctas, pts, banco)


def _filas_a_preguntas(filas: list[list], banco: str) -> list[Pregunta]:
    """Primera fila = encabezados: Pregunta | Tipo | A | B | C ... | Correcta | Puntos."""
    filas = [f for f in filas if any(str(c or "").strip() for c in f)]
    if not filas:
        return []
    enc = [normalizar(c) for c in filas[0]]

    def col(*nombres):
        for i, h in enumerate(enc):
            if h in nombres:
                return i
        return None

    c_preg = col("pregunta", "enunciado", "texto", "question")
    c_tipo = col("tipo", "type")
    c_corr = col("correcta", "respuesta", "respuesta correcta", "clave", "answer", "correct")
    c_pts = col("puntos", "puntaje", "valor", "points")
    c_ops = []
    for i, h in enumerate(enc):
        m = re.fullmatch(r"(?:opcion|opción|op|option)?\s*([a-j])", h)
        if m:
            c_ops.append((m.group(1).upper(), i))
    if c_preg is None or c_corr is None:
        raise ValueError("El archivo necesita al menos las columnas «Pregunta» y «Correcta». "
                         "Usa la plantilla de Excel del panel.")

    def val(fila, i):
        return fila[i] if i is not None and i < len(fila) and fila[i] is not None else ""

    preguntas = []
    for n, fila in enumerate(filas[1:], start=1):
        opciones = [(l, str(val(fila, i)).strip()) for l, i in c_ops if str(val(fila, i)).strip()]
        p = _armar(n, banco, val(fila, c_preg), val(fila, c_tipo), opciones, val(fila, c_corr), val(fila, c_pts))
        if p:
            preguntas.append(p)
    return preguntas


def _leer_aiken(texto: str, banco: str) -> list[Pregunta]:
    """Formato Aiken (compatible con Moodle) + extensiones:
        Pregunta…            A. opción         ANSWER: B   (o RESPUESTA: B / A,C / V / texto1|texto2)
        PUNTOS: 2            (opcional)        TIPO: abierta (opcional)
    Bloques separados por una línea en blanco."""
    preguntas, n = [], 0
    for bloque in re.split(r"\n\s*\n", texto.replace("\r\n", "\n").strip()):
        lineas = [l.rstrip() for l in bloque.split("\n") if l.strip()]
        if not lineas:
            continue
        enunciado, opciones, correcta, puntos, tipo = [], [], "", "", ""
        for l in lineas:
            m_op = re.match(r"^\s*([A-Ja-j])[\.\)]\s+(.*)$", l)
            m_kv = re.match(r"^\s*(ANSWER|RESPUESTA|CORRECTA|PUNTOS|POINTS|TIPO)\s*:\s*(.*)$", l, re.I)
            if m_kv:
                k, v = m_kv.group(1).upper(), m_kv.group(2).strip()
                if k in ("ANSWER", "RESPUESTA", "CORRECTA"):
                    correcta = v
                elif k == "TIPO":
                    tipo = v
                else:
                    puntos = v
            elif m_op and not correcta:
                opciones.append((m_op.group(1).upper(), m_op.group(2).strip()))
            elif not opciones:
                enunciado.append(l.strip())
        n += 1
        p = _armar(n, banco, "\n".join(enunciado), tipo, opciones, correcta, puntos)
        if p:
            preguntas.append(p)
    return preguntas


def cargar_banco(ruta: str) -> list[Pregunta]:
    banco = os.path.splitext(os.path.basename(ruta))[0]
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(ruta, read_only=True, data_only=True)
        preguntas = []
        for ws in wb.worksheets:
            filas = [list(r) for r in ws.iter_rows(values_only=True)]
            try:
                preguntas += _filas_a_preguntas(filas, banco if len(wb.worksheets) == 1 else f"{banco}/{ws.title}")
            except ValueError:
                if ws is wb.worksheets[0]:
                    raise
        wb.close()
        return preguntas
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(ruta, encoding=enc) as f:
                contenido = f.read()
            break
        except UnicodeDecodeError:
            continue
    if ext == ".csv":
        dialecto = csv.Sniffer().sniff(contenido[:2000], delimiters=",;\t")
        return _filas_a_preguntas(list(csv.reader(contenido.splitlines(), dialecto)), banco)
    return _leer_aiken(contenido, banco)


def crear_plantilla(ruta: str):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Preguntas"
    ws.append(["Pregunta", "Tipo", "A", "B", "C", "D", "E", "Correcta", "Puntos"])
    ws.append(["¿Cuál es la capital de Francia?", "opcion", "Madrid", "París", "Roma", "Berlín", "", "B", 1])
    ws.append(["Selecciona los números primos", "multiple", "2", "4", "7", "9", "", "A,C", 2])
    ws.append(["El agua hierve a 100 °C al nivel del mar", "vf", "", "", "", "", "", "V", 1])
    ws.append(["¿Quién escribió Don Quijote?", "abierta", "", "", "", "", "", "Cervantes|Miguel de Cervantes", 1])
    ws.append(["Explica con tus palabras qué es la fotosíntesis", "abierta", "", "", "", "", "", "", 3])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1E3A8A")
    for letra, ancho in zip("ABCDEFGHI", (48, 10, 16, 16, 16, 16, 16, 30, 8)):
        ws.column_dimensions[letra].width = ancho
    ws.freeze_panes = "A2"
    ayuda = wb.create_sheet("Ayuda")
    for linea in [
        "Tipo: opcion (una correcta) · multiple (varias, separadas por coma: A,C) · vf (V o F) · abierta",
        "Abierta: escribe las respuestas aceptadas separadas por | para calificar sola; vacío = revisión manual.",
        "Puntos: opcional (1 por defecto). Las columnas A a J son las opciones.",
        "Solo se lee la hoja 'Preguntas' (y otras hojas con el mismo formato).",
    ]:
        ayuda.append([linea])
    ayuda.column_dimensions["A"].width = 110
    wb.save(ruta)


# ----------------------------------------------------------------- examen

@dataclass
class Estudiante:
    token: str
    nombre: str
    dispositivo: str
    modelo: str
    ip: str
    inicio: float
    preguntas: list[str]
    orden_opciones: dict[str, list[str]]
    respuestas: dict = field(default_factory=dict)
    estado: str = "activo"          # activo | entregado | terminado | tiempo | cerrado
    motivo: str = ""
    fin: float | None = None
    ultimo_latido: float = 0.0
    incidentes: int = 0
    advertencias: int = 0
    puntaje: float = 0.0
    maximo: float = 0.0
    pendientes: int = 0
    reingreso: bool = False

    @property
    def activo(self):
        return self.estado == "activo"


ESTADOS = {
    "activo": "En curso",
    "entregado": "Entregado",
    "terminado": "TERMINADO (salió)",
    "tiempo": "Tiempo agotado",
    "cerrado": "Cerrado por docente",
}


class Examen:
    def __init__(self, titulo: str, preguntas: list[Pregunta], cantidad: int, duracion_min: int,
                 mezclar_preguntas: bool, mezclar_opciones: bool, mostrar_nota: bool,
                 exigir_bloqueo: bool, carpeta_base: str):
        if not preguntas:
            raise ValueError("No hay preguntas cargadas.")
        self.titulo = titulo.strip() or "Examen"
        from dataclasses import replace
        self.banco = {f"P{k}": replace(p, id=f"P{k}") for k, p in enumerate(preguntas, 1)}
        self.cantidad = min(cantidad, len(preguntas)) if cantidad > 0 else len(preguntas)
        self.duracion = max(0, duracion_min) * 60
        self.mezclar_preguntas = mezclar_preguntas
        self.mezclar_opciones = mezclar_opciones
        self.mostrar_nota = mostrar_nota
        self.exigir_bloqueo = exigir_bloqueo
        self.codigo = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        self.abierto = True
        self.creado = time.time()
        self.estudiantes: dict[str, Estudiante] = {}
        self.eventos: list[tuple[str, str, str, str]] = []  # hora, nombre, tipo, detalle
        self.lock = threading.RLock()
        self.version = 0
        seguro = re.sub(r"[^\w\- ]", "", self.titulo).strip().replace(" ", "_")[:40] or "Examen"
        self.carpeta = os.path.join(carpeta_base, f"{dt.datetime.now():%Y-%m-%d_%H%M}_{seguro}_{self.codigo}")
        os.makedirs(self.carpeta, exist_ok=True)
        self.guardado = Guardado(self)
        self.evento("", "info", f"Examen «{self.titulo}» abierto · código {self.codigo} · "
                                f"{self.cantidad} preguntas · duración "
                                f"{(str(duracion_min) + ' min') if self.duracion else 'sin límite'}")

    # ---- registro
    def evento(self, nombre: str, tipo: str, detalle: str):
        with self.lock:
            fila = (ahora(), nombre, tipo, detalle)
            self.eventos.append(fila)
            self.version += 1
        self.guardado.anotar(fila)

    def _cambio(self):
        self.version += 1
        self.guardado.marcar()

    # ---- estudiante
    def unirse(self, nombre: str, codigo: str, dispositivo: str, modelo: str, ip: str) -> tuple[int, dict]:
        nombre = re.sub(r"\s+", " ", (nombre or "")).strip()
        with self.lock:
            if (codigo or "").strip().upper() != self.codigo:
                return 404, {"error": "Código de examen inválido. Vuelve a escanear el QR."}
            if not self.abierto:
                return 403, {"error": "El examen ya está cerrado."}
            if len(nombre) < 5 or " " not in nombre:
                return 400, {"error": "Escribe tu nombre completo (nombre y apellidos)."}
            clave = normalizar(nombre)
            existente = next((e for e in self.estudiantes.values() if normalizar(e.nombre) == clave), None)
            mismo_disp = next((e for e in self.estudiantes.values()
                               if dispositivo and e.dispositivo == dispositivo and e is not existente), None)
            if mismo_disp and not mismo_disp.reingreso:
                self.evento(nombre, "incidente",
                            f"Intentó entrar desde el dispositivo ya usado por {mismo_disp.nombre}")
                return 409, {"error": f"Este dispositivo ya se usó en el examen como «{mismo_disp.nombre}»."}
            if existente:
                if existente.reingreso:
                    existente.reingreso = False
                    existente.estado = "activo"
                    existente.motivo = ""
                    existente.fin = None
                    existente.dispositivo, existente.modelo, existente.ip = dispositivo, modelo, ip
                    self.evento(existente.nombre, "info", "Reingresó (autorizado por el docente)")
                elif existente.activo:
                    if existente.dispositivo != dispositivo:
                        self.evento(nombre, "incidente", "Intentó entrar con un nombre ya conectado en otro dispositivo")
                        return 409, {"error": "Ese nombre ya está conectado en otro dispositivo. Avisa al docente."}
                    self.evento(existente.nombre, "info", "Se reconectó")
                else:
                    return 403, {"error": f"Ya no puedes entrar: {ESTADOS[existente.estado].lower()}. "
                                          "Si es un error, pide al docente que autorice tu reingreso."}
                existente.ultimo_latido = time.time()
                self._cambio()
                return 200, self._bienvenida(existente)

            ids = list(self.banco)
            if self.mezclar_preguntas:
                random.shuffle(ids)
            ids = ids[: self.cantidad]
            orden = {}
            for i in ids:
                ops = [o for o, _ in self.banco[i].opciones]
                if self.mezclar_opciones and self.banco[i].tipo in ("opcion", "multiple"):
                    random.shuffle(ops)
                orden[i] = ops
            est = Estudiante(secrets.token_urlsafe(18), nombre, dispositivo, modelo, ip,
                             time.time(), ids, orden, ultimo_latido=time.time())
            est.maximo = sum(self.banco[i].puntos for i in ids)
            self.estudiantes[est.token] = est
            self.evento(nombre, "info", f"Se unió desde {modelo or 'dispositivo desconocido'} ({ip})")
            self._cambio()
            return 200, self._bienvenida(est)

    def _bienvenida(self, e: Estudiante) -> dict:
        return {"token": e.token, "url": f"/examen?t={e.token}", "titulo": self.titulo,
                "nombre": e.nombre, "bloqueo": self.exigir_bloqueo}

    def restante(self, e: Estudiante) -> int | None:
        if not self.duracion:
            return None
        return max(0, int(e.inicio + self.duracion - time.time()))

    def _vigente(self, token: str) -> Estudiante | None:
        e = self.estudiantes.get(token)
        if e and e.activo and self.duracion and self.restante(e) == 0:
            self.entregar(token, "tiempo", "Se agotó el tiempo")
        return e

    def datos(self, token: str) -> dict | None:
        with self.lock:
            e = self._vigente(token)
            if not e:
                return None
            return {
                "titulo": self.titulo, "nombre": e.nombre, "estado": e.estado,
                "restante": self.restante(e),
                "preguntas": [self.banco[i].publica(e.orden_opciones.get(i)) for i in e.preguntas],
                "respuestas": e.respuestas,
            }

    def responder(self, token: str, pregunta: str, valor) -> tuple[int, dict]:
        with self.lock:
            e = self._vigente(token)
            if not e:
                return 404, {"error": "Sesión inválida"}
            if not e.activo:
                return 409, {"estado": e.estado}
            if pregunta not in e.preguntas:
                return 400, {"error": "Pregunta inválida"}
            p = self.banco[pregunta]
            if p.tipo == "abierta":
                valor = str(valor or "")[:5000]
            elif p.tipo == "multiple":
                valor = [v for v in (valor if isinstance(valor, list) else []) if v in dict(p.opciones)]
            else:
                valor = valor if valor in dict(p.opciones) else ""
            e.respuestas[pregunta] = valor
            e.ultimo_latido = time.time()
            self._cambio()
            return 200, {"ok": True, "contestadas": self._contestadas(e)}

    @staticmethod
    def _contestadas(e: Estudiante) -> int:
        return sum(1 for v in e.respuestas.values() if v not in ("", [], None))

    def latido(self, token: str) -> dict | None:
        with self.lock:
            e = self._vigente(token)
            if not e:
                return None
            e.ultimo_latido = time.time()
            if e.activo and not self.abierto:
                self.entregar(token, "cerrado", "El docente cerró el examen")
            return {"estado": e.estado, "restante": self.restante(e)}

    def telemetria(self, token: str, tipo: str, detalle: str):
        with self.lock:
            e = self.estudiantes.get(token)
            if not e:
                return False
            tipo = tipo if tipo in ("info", "advertencia", "incidente", "aviso") else "info"
            if tipo == "incidente":
                e.incidentes += 1
            elif tipo == "advertencia":
                e.advertencias += 1
            e.ultimo_latido = time.time()
            self.evento(e.nombre, tipo, str(detalle)[:500])
            self._cambio()
            return True

    def entregar(self, token: str, estado: str = "entregado", motivo: str = "") -> dict | None:
        with self.lock:
            e = self.estudiantes.get(token)
            if not e:
                return None
            if e.activo:
                e.estado, e.motivo, e.fin = estado, motivo, time.time()
                self._calificar(e)
                tipo = "incidente" if estado == "terminado" else "info"
                self.evento(e.nombre, tipo, f"{ESTADOS[estado]}{': ' + motivo if motivo else ''} · "
                                            f"puntaje {e.puntaje:g}/{e.maximo:g}"
                                            f"{f' (+{e.pendientes} por revisar)' if e.pendientes else ''}")
                self._cambio()
            return self.resultado(e)

    def resultado(self, e: Estudiante) -> dict:
        r = {"estado": e.estado, "estado_texto": ESTADOS[e.estado], "motivo": e.motivo,
             "contestadas": self._contestadas(e), "total": len(e.preguntas), "nombre": e.nombre}
        if self.mostrar_nota and not e.activo:
            r.update(puntaje=e.puntaje, maximo=e.maximo, pendientes=e.pendientes)
        return r

    def _calificar(self, e: Estudiante):
        total, pend = 0.0, 0
        for i in e.preguntas:
            pts = self.banco[i].calificar(e.respuestas.get(i))
            if pts is None:
                pend += 1
            else:
                total += pts
        e.puntaje, e.pendientes = round(total, 2), pend

    # ---- acciones del docente
    def cerrar(self):
        with self.lock:
            self.abierto = False
            for t, e in list(self.estudiantes.items()):
                if e.activo:
                    self.entregar(t, "cerrado", "El docente cerró el examen")
            self.evento("", "info", "Examen cerrado por el docente")
        self.guardado.guardar_ahora()

    def permitir_reingreso(self, token: str):
        with self.lock:
            e = self.estudiantes.get(token)
            if e and not e.activo:
                e.reingreso = True
                self.evento(e.nombre, "info", "El docente autorizó su reingreso")
                self._cambio()

    def terminar_estudiante(self, token: str):
        self.entregar(token, "cerrado", "El docente terminó su examen")

    def revisar_tiempos(self):
        with self.lock:
            for t in list(self.estudiantes):
                self._vigente(t)

    def resumen(self) -> list[dict]:
        with self.lock:
            ahora_ts = time.time()
            filas = []
            for e in sorted(self.estudiantes.values(), key=lambda x: normalizar(x.nombre)):
                sin_senal = e.activo and ahora_ts - e.ultimo_latido > 20
                filas.append({
                    "token": e.token, "nombre": e.nombre,
                    "estado": ESTADOS[e.estado] + (" · sin señal" if sin_senal else ""),
                    "clave": "sinsenal" if sin_senal else e.estado,
                    "progreso": f"{self._contestadas(e)}/{len(e.preguntas)}",
                    "incidentes": e.incidentes, "advertencias": e.advertencias,
                    "puntaje": "" if e.activo else f"{e.puntaje:g}/{e.maximo:g}" + (" *" if e.pendientes else ""),
                    "restante": self._fmt_restante(e),
                    "modelo": e.modelo,
                })
            return filas

    def _fmt_restante(self, e):
        if not e.activo:
            return ""
        r = self.restante(e)
        return "—" if r is None else f"{r // 60}:{r % 60:02d}"

    def detalle(self, token: str) -> str:
        with self.lock:
            e = self.estudiantes.get(token)
            return self.guardado.bloque_txt(e) if e else ""


# ----------------------------------------------------------------- guardado

class Guardado:
    """Escribe en la carpeta del examen:
      telemetria.txt  — en vivo, una línea por evento
      resultados.txt  — resumen y respuestas de cada estudiante
      resultados.xlsx — hojas Resumen, Respuestas, Telemetría y Preguntas"""

    def __init__(self, examen: Examen):
        self.x = examen
        self.sucio = threading.Event()
        self.lock_txt = threading.Lock()
        self.error = ""
        self.ultimo_guardado = ""
        self.ruta_tel = os.path.join(examen.carpeta, "telemetria.txt")
        self.ruta_txt = os.path.join(examen.carpeta, "resultados.txt")
        self.ruta_xlsx = os.path.join(examen.carpeta, "resultados.xlsx")
        threading.Thread(target=self._bucle, daemon=True).start()

    def anotar(self, fila):
        hora, nombre, tipo, detalle = fila
        with self.lock_txt, open(self.ruta_tel, "a", encoding="utf-8") as f:
            f.write(f"{dt.date.today()} {hora}\t{tipo.upper():<11}\t{nombre or '-'}\t{detalle}\n")
        self.sucio.set()

    def marcar(self):
        self.sucio.set()

    def _bucle(self):
        while True:
            self.sucio.wait()
            time.sleep(2)  # agrupa cambios
            self.sucio.clear()
            self.guardar_ahora()

    def guardar_ahora(self):
        with self.x.lock:
            ests = sorted(self.x.estudiantes.values(), key=lambda e: normalizar(e.nombre))
            for e in ests:
                if e.activo:
                    self.x._calificar(e)  # puntaje parcial para el reporte
            eventos = list(self.x.eventos)
            txt = self._txt(ests)
            libro = self._xlsx(ests, eventos)
        with open(self.ruta_txt, "w", encoding="utf-8") as f:
            f.write(txt)
        try:
            libro.save(self.ruta_xlsx)
            self.error = ""
            self.ultimo_guardado = ahora()
        except PermissionError:
            self.error = "resultados.xlsx está abierto en Excel: ciérralo para que se actualice."
            self.sucio.set()

    # ---- TXT
    def bloque_txt(self, e: Estudiante) -> str:
        x = self.x
        dur = int(((e.fin or time.time()) - e.inicio) // 60)
        l = [f"{'=' * 70}", f"ESTUDIANTE: {e.nombre}",
             f"Estado: {ESTADOS[e.estado]}{' — ' + e.motivo if e.motivo else ''}",
             f"Puntaje: {e.puntaje:g} / {e.maximo:g}" + (f"  ({e.pendientes} por revisar manualmente)" if e.pendientes else ""),
             f"Calificación (0-10): {self._nota(e)}",
             f"Inicio: {fecha_hora(e.inicio)}   Fin: {fecha_hora(e.fin)}   Duración: {dur} min",
             f"Incidentes: {e.incidentes}   Advertencias: {e.advertencias}   Dispositivo: {e.modelo} ({e.ip})",
             "-" * 70]
        for n, i in enumerate(e.preguntas, 1):
            p = x.banco[i]
            v = e.respuestas.get(i)
            pts = p.calificar(v)
            marca = "REVISAR" if pts is None else ("✔" if pts == p.puntos else "✘")
            l.append(f"{n}. [{marca}] {p.texto}")
            l.append(f"   Respuesta: {p.texto_respuesta(v) or '(sin responder)'}")
            l.append(f"   Correcta:  {p.texto_correcta()}   Puntos: {'' if pts is None else f'{pts:g}'}/{p.puntos:g}")
        incid = [ev for ev in x.eventos if ev[1] == e.nombre and ev[2] in ("incidente", "advertencia")]
        if incid:
            l.append("-" * 70 + "\nTELEMETRÍA:")
            l += [f"   {h}  {t.upper():<11} {d}" for h, _, t, d in incid]
        return "\n".join(l) + "\n"

    def _txt(self, ests) -> str:
        x = self.x
        cab = [f"EXAMEN: {x.titulo}", f"Código: {x.codigo}   Creado: {fecha_hora(x.creado)}",
               f"Preguntas por estudiante: {x.cantidad}   Duración: "
               f"{x.duracion // 60 if x.duracion else 'sin límite'} min", f"Estudiantes: {len(ests)}", ""]
        cab.append(f"{'NOMBRE':<35} {'ESTADO':<22} {'PUNTAJE':>10} {'NOTA':>5} {'INCID.':>6}")
        for e in ests:
            cab.append(f"{e.nombre[:35]:<35} {ESTADOS[e.estado][:22]:<22} "
                       f"{f'{e.puntaje:g}/{e.maximo:g}':>10} {self._nota(e):>5} {e.incidentes:>6}")
        return "\n".join(cab) + "\n\n" + "\n".join(self.bloque_txt(e) for e in ests)

    @staticmethod
    def _nota(e: Estudiante) -> str:
        return f"{(10 * e.puntaje / e.maximo):.1f}" if e.maximo else "-"

    # ---- Excel
    def _xlsx(self, ests, eventos):
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        x = self.x
        wb = Workbook()
        cab_font = Font(bold=True, color="FFFFFF")
        cab_fill = PatternFill("solid", fgColor="1E3A8A")
        rojo = PatternFill("solid", fgColor="FDE2E2")
        verde = PatternFill("solid", fgColor="DCFCE7")
        amarillo = PatternFill("solid", fgColor="FEF3C7")

        def hoja(ws, encabezados, anchos):
            ws.append(encabezados)
            for c in ws[1]:
                c.font, c.fill = cab_font, cab_fill
            for i, a in enumerate(anchos):
                ws.column_dimensions[chr(65 + i)].width = a
            ws.freeze_panes = "A2"

        ws = wb.active
        ws.title = "Resumen"
        hoja(ws, ["Nombre", "Estado", "Motivo", "Puntaje", "Máximo", "%", "Calificación (0-10)",
                  "Por revisar", "Contestadas", "Incidentes", "Advertencias", "Inicio", "Fin",
                  "Duración (min)", "Dispositivo", "IP"],
             [32, 20, 34, 9, 9, 7, 12, 10, 11, 10, 11, 19, 19, 12, 22, 15])
        for e in ests:
            pct = round(100 * e.puntaje / e.maximo, 1) if e.maximo else 0
            ws.append([e.nombre, ESTADOS[e.estado], e.motivo, e.puntaje, e.maximo, pct,
                       float(self._nota(e)) if e.maximo else None, e.pendientes,
                       f"{x._contestadas(e)}/{len(e.preguntas)}", e.incidentes, e.advertencias,
                       fecha_hora(e.inicio), fecha_hora(e.fin),
                       round(((e.fin or time.time()) - e.inicio) / 60, 1), e.modelo, e.ip])
            fill = rojo if e.estado == "terminado" else (amarillo if e.incidentes else None)
            if fill:
                for c in ws[ws.max_row]:
                    c.fill = fill
        ws.auto_filter.ref = ws.dimensions

        ws = wb.create_sheet("Respuestas")
        hoja(ws, ["Nombre", "Nº", "Pregunta", "Tipo", "Respuesta del estudiante", "Respuesta correcta",
                  "Resultado", "Puntos", "Puntos posibles", "Banco"],
             [30, 5, 60, 10, 40, 40, 12, 8, 10, 18])
        for e in ests:
            for n, i in enumerate(e.preguntas, 1):
                p = x.banco[i]
                v = e.respuestas.get(i)
                pts = p.calificar(v)
                res = "Revisar" if pts is None else ("Correcta" if pts == p.puntos else
                                                     ("Sin responder" if v in (None, "", []) else "Incorrecta"))
                ws.append([e.nombre, n, p.texto, p.tipo, p.texto_respuesta(v), p.texto_correcta(),
                           res, pts, p.puntos, p.banco])
                ws.cell(ws.max_row, 7).fill = verde if res == "Correcta" else (amarillo if res == "Revisar" else rojo)
                ws.cell(ws.max_row, 3).alignment = Alignment(wrap_text=True, vertical="top")
        ws.auto_filter.ref = ws.dimensions

        ws = wb.create_sheet("Telemetría")
        hoja(ws, ["Fecha", "Hora", "Estudiante", "Tipo", "Detalle"], [12, 10, 30, 12, 90])
        hoy = str(dt.date.today())
        for h, nombre, tipo, det in eventos:
            ws.append([hoy, h, nombre, tipo, det])
            if tipo == "incidente":
                ws.cell(ws.max_row, 4).fill = rojo
            elif tipo == "advertencia":
                ws.cell(ws.max_row, 4).fill = amarillo
        ws.auto_filter.ref = ws.dimensions

        ws = wb.create_sheet("Preguntas")
        hoja(ws, ["ID", "Banco", "Tipo", "Pregunta", "Opciones", "Correcta", "Puntos"], [14, 18, 10, 60, 50, 30, 8])
        for p in x.banco.values():
            ws.append([p.id, p.banco, p.tipo, p.texto, " | ".join(f"{o}) {t}" for o, t in p.opciones),
                       p.texto_correcta(), p.puntos])
        return wb
