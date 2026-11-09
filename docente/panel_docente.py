"""Examen Seguro — Panel del docente.

Ejecuta:  python panel_docente.py
La PC actúa como servidor en la red local; los teléfonos escanean el QR y se conectan.
"""

from __future__ import annotations

import base64
import io
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import segno

import nucleo
import servidor_red
from servidor_red import Estado

CARPETA_RESULTADOS = os.path.join(os.path.expanduser("~"), "Documents", "ExamenSeguro", "Resultados")
CARPETA_BANCOS = os.path.join(os.path.expanduser("~"), "Documents", "ExamenSeguro", "Bancos")

COLORES = {
    "activo": "#ffffff", "entregado": "#dcfce7", "terminado": "#fecaca",
    "tiempo": "#e0e7ff", "cerrado": "#e5e7eb", "sinsenal": "#fef3c7",
}


def abrir(ruta: str):
    if sys.platform == "win32":
        os.startfile(ruta)  # noqa: S606
    else:
        import subprocess
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", ruta])


def imagen_qr(texto: str, escala: int) -> tk.PhotoImage:
    buf = io.BytesIO()
    segno.make(texto, error="m").save(buf, kind="png", scale=escala, border=2)
    return tk.PhotoImage(data=base64.b64encode(buf.getvalue()))


class Panel(tk.Tk):
    def __init__(self, puerto: int):
        super().__init__()
        self.puerto = puerto
        self.title("Examen Seguro — Panel del docente")
        self.geometry("1280x800")
        self.minsize(960, 600)
        if sys.platform == "win32":
            self.state("zoomed")  # maximizada
        self.bancos: dict[str, list[nucleo.Pregunta]] = {}
        self.version_vista = -1
        self.qr_img = None
        self._estilos()
        self._construir()
        self.after(1000, self._refrescar)
        self.protocol("WM_DELETE_WINDOW", self._salir)

    # ------------------------------------------------------------------ UI
    def _estilos(self):
        s = ttk.Style(self)
        if "vista" in s.theme_names():
            s.theme_use("vista")
        s.configure("Titulo.TLabel", font=("Segoe UI", 16, "bold"))
        s.configure("Codigo.TLabel", font=("Consolas", 26, "bold"), foreground="#1e3a8a")
        s.configure("Grande.TButton", font=("Segoe UI", 11, "bold"), padding=8)
        s.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

    def _construir(self):
        sup = ttk.Frame(self, padding=(12, 10))
        sup.pack(fill="x")
        ttk.Label(sup, text="Examen Seguro", style="Titulo.TLabel").pack(side="left")
        ttk.Label(sup, text="   IP para el QR:").pack(side="left")
        self.ips = servidor_red.ips_locales()
        self.var_ip = tk.StringVar(value=self.ips[0])
        cb = ttk.Combobox(sup, textvariable=self.var_ip, values=self.ips, width=16, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._pintar_qr())
        ttk.Label(sup, text=f"  Puerto: {self.puerto}").pack(side="left")
        self.lbl_estado = ttk.Label(sup, text="", foreground="#b45309")
        self.lbl_estado.pack(side="right")

        cuerpo = ttk.Frame(self, padding=(12, 0, 12, 12))
        cuerpo.pack(fill="both", expand=True)
        izq = ttk.Frame(cuerpo, width=380)
        izq.pack(side="left", fill="y")
        izq.pack_propagate(False)
        der = ttk.Frame(cuerpo)
        der.pack(side="left", fill="both", expand=True, padx=(12, 0))

        # 1. Bancos
        f1 = ttk.LabelFrame(izq, text=" 1. Bancos de preguntas ", padding=8)
        f1.pack(fill="x")
        self.lst_bancos = tk.Listbox(f1, height=5, activestyle="none", font=("Segoe UI", 10))
        self.lst_bancos.pack(fill="x")
        b = ttk.Frame(f1)
        b.pack(fill="x", pady=(6, 0))
        ttk.Button(b, text="Cargar banco…", command=self._cargar_banco).pack(side="left")
        ttk.Button(b, text="Quitar", command=self._quitar_banco).pack(side="left", padx=4)
        ttk.Button(b, text="Plantilla Excel", command=self._plantilla).pack(side="left")
        self.lbl_total = ttk.Label(f1, text="0 preguntas cargadas", foreground="#6b7280")
        self.lbl_total.pack(anchor="w", pady=(6, 0))

        # 2. Examen
        f2 = ttk.LabelFrame(izq, text=" 2. Examen ", padding=8)
        f2.pack(fill="x", pady=8)
        f2.columnconfigure(1, weight=1)
        self.var_titulo = tk.StringVar(value="Examen")
        self.var_cant = tk.IntVar(value=0)
        self.var_dur = tk.IntVar(value=60)
        ttk.Label(f2, text="Título").grid(row=0, column=0, sticky="w")
        ttk.Entry(f2, textvariable=self.var_titulo).grid(row=0, column=1, sticky="ew", pady=2)
        ttk.Label(f2, text="Preguntas (0 = todas)").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(f2, from_=0, to=500, textvariable=self.var_cant, width=8).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(f2, text="Duración en min (0 = sin límite)").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(f2, from_=0, to=600, textvariable=self.var_dur, width=8).grid(row=2, column=1, sticky="w", pady=2)
        self.var_mp = tk.BooleanVar(value=True)
        self.var_mo = tk.BooleanVar(value=True)
        self.var_nota = tk.BooleanVar(value=False)
        self.var_bloq = tk.BooleanVar(value=True)
        self.var_nav = tk.BooleanVar(value=False)
        for i, (t, v) in enumerate([("Mezclar preguntas (cada alumno, distinto orden)", self.var_mp),
                                    ("Mezclar opciones", self.var_mo),
                                    ("Mostrar calificación al entregar", self.var_nota),
                                    ("Exigir fijar pantalla en el teléfono", self.var_bloq),
                                    ("Permitir navegadores normales (solo pruebas)", self.var_nav)], start=3):
            ttk.Checkbutton(f2, text=t, variable=v, command=self._sync_nav).grid(row=i, column=0, columnspan=2, sticky="w")
        bb = ttk.Frame(f2)
        bb.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.btn_iniciar = ttk.Button(bb, text="▶  Iniciar examen", style="Grande.TButton", command=self._iniciar)
        self.btn_iniciar.pack(side="left", fill="x", expand=True)
        self.btn_cerrar = ttk.Button(bb, text="■  Cerrar examen", style="Grande.TButton",
                                     command=self._cerrar, state="disabled")
        self.btn_cerrar.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # 3. Conexión
        f3 = ttk.LabelFrame(izq, text=" 3. Conexión de los estudiantes ", padding=8)
        f3.pack(fill="both", expand=True)
        self.lbl_qr = ttk.Label(f3, text="Inicia un examen para generar el QR", anchor="center")
        self.lbl_qr.pack(fill="both", expand=True)
        self.lbl_codigo = ttk.Label(f3, text="", style="Codigo.TLabel", anchor="center")
        self.lbl_codigo.pack(fill="x")
        self.lbl_url = ttk.Label(f3, text="", foreground="#6b7280", anchor="center")
        self.lbl_url.pack(fill="x")
        bq = ttk.Frame(f3)
        bq.pack(fill="x", pady=(6, 0))
        ttk.Button(bq, text="QR en pantalla completa", command=self._qr_grande).pack(side="left", fill="x", expand=True)
        ttk.Button(bq, text="Abrir carpeta de resultados", command=self._abrir_resultados).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

        # Derecha: estudiantes y telemetría
        self.lbl_conteo = ttk.Label(der, text="Sin examen activo", font=("Segoe UI", 11, "bold"))
        self.lbl_conteo.pack(anchor="w")
        nb = ttk.Notebook(der)
        nb.pack(fill="both", expand=True, pady=(6, 0))

        t1 = ttk.Frame(nb, padding=6)
        nb.add(t1, text="  Estudiantes  ")
        cols = ("nombre", "estado", "progreso", "restante", "incidentes", "advertencias", "puntaje", "modelo")
        self.tv = ttk.Treeview(t1, columns=cols, show="headings", selectmode="browse")
        for c, t, w in zip(cols, ("Nombre completo", "Estado", "Progreso", "Tiempo", "Incidentes",
                                  "Advertencias", "Puntaje", "Dispositivo"),
                           (240, 200, 80, 70, 80, 90, 90, 160)):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor="w" if c in ("nombre", "estado", "modelo") else "center")
        for k, color in COLORES.items():
            self.tv.tag_configure(k, background=color)
        sb = ttk.Scrollbar(t1, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="top", fill="both", expand=True)
        self.tv.bind("<Double-1>", lambda e: self._ver_detalle())
        be = ttk.Frame(t1)
        be.pack(fill="x", pady=(6, 0))
        ttk.Button(be, text="Ver respuestas y telemetría", command=self._ver_detalle).pack(side="left")
        ttk.Button(be, text="Permitir reingreso", command=self._reingreso).pack(side="left", padx=6)
        ttk.Button(be, text="Terminar examen de este estudiante", command=self._terminar_uno).pack(side="left")

        t2 = ttk.Frame(nb, padding=6)
        nb.add(t2, text="  Telemetría  ")
        filtro = ttk.Frame(t2)
        filtro.pack(fill="x")
        ttk.Label(filtro, text="Mostrar:").pack(side="left")
        self.var_filtro = tk.StringVar(value="todo")
        for t, v in (("Todo", "todo"), ("Advertencias e incidentes", "alertas"), ("Solo incidentes", "incidente")):
            ttk.Radiobutton(filtro, text=t, value=v, variable=self.var_filtro,
                            command=lambda: self._pintar_eventos(True)).pack(side="left", padx=4)
        cols2 = ("hora", "nombre", "tipo", "detalle")
        self.tv_ev = ttk.Treeview(t2, columns=cols2, show="headings")
        for c, t, w in zip(cols2, ("Hora", "Estudiante", "Tipo", "Detalle"), (80, 220, 100, 700)):
            self.tv_ev.heading(c, text=t)
            self.tv_ev.column(c, width=w, anchor="w")
        self.tv_ev.tag_configure("incidente", background="#fecaca")
        self.tv_ev.tag_configure("advertencia", background="#fef3c7")
        self.tv_ev.tag_configure("aviso", background="#e0e7ff")
        self.tv_ev.pack(fill="both", expand=True, pady=(6, 0))
        self.n_eventos = 0

    # ------------------------------------------------------------------ bancos
    def _cargar_banco(self):
        os.makedirs(CARPETA_BANCOS, exist_ok=True)
        rutas = filedialog.askopenfilenames(
            title="Cargar banco de preguntas", initialdir=CARPETA_BANCOS,
            filetypes=[("Bancos de preguntas", "*.xlsx *.xlsm *.csv *.txt"), ("Excel", "*.xlsx *.xlsm"),
                       ("CSV", "*.csv"), ("Texto (formato Aiken)", "*.txt")])
        for ruta in rutas:
            try:
                preguntas = nucleo.cargar_banco(ruta)
            except Exception as e:  # noqa: BLE001 — se muestra al docente
                messagebox.showerror("No se pudo cargar", f"{os.path.basename(ruta)}\n\n{e}")
                continue
            if not preguntas:
                messagebox.showwarning("Banco vacío", f"{os.path.basename(ruta)} no tiene preguntas reconocibles.")
                continue
            self.bancos[ruta] = preguntas
        self._pintar_bancos()

    def _quitar_banco(self):
        sel = self.lst_bancos.curselection()
        if sel:
            del self.bancos[list(self.bancos)[sel[0]]]
            self._pintar_bancos()

    def _pintar_bancos(self):
        self.lst_bancos.delete(0, "end")
        for ruta, ps in self.bancos.items():
            tipos = {}
            for p in ps:
                tipos[p.tipo] = tipos.get(p.tipo, 0) + 1
            det = ", ".join(f"{n} {t}" for t, n in tipos.items())
            self.lst_bancos.insert("end", f"{os.path.basename(ruta)} — {len(ps)} ({det})")
        total = sum(len(p) for p in self.bancos.values())
        self.lbl_total.configure(text=f"{total} preguntas cargadas")
        if self.bancos and self.var_titulo.get() == "Examen":
            self.var_titulo.set(os.path.splitext(os.path.basename(next(iter(self.bancos))))[0])

    def _plantilla(self):
        os.makedirs(CARPETA_BANCOS, exist_ok=True)
        ruta = filedialog.asksaveasfilename(title="Guardar plantilla", initialdir=CARPETA_BANCOS,
                                            initialfile="banco_plantilla.xlsx", defaultextension=".xlsx",
                                            filetypes=[("Excel", "*.xlsx")])
        if ruta:
            nucleo.crear_plantilla(ruta)
            abrir(ruta)

    # ------------------------------------------------------------------ examen
    def _sync_nav(self):
        Estado.permitir_navegador = self.var_nav.get()

    def _iniciar(self):
        if Estado.examen and Estado.examen.abierto:
            return
        preguntas = [p for ps in self.bancos.values() for p in ps]
        if not preguntas:
            messagebox.showinfo("Faltan preguntas", "Primero carga al menos un banco de preguntas.")
            return
        try:
            x = nucleo.Examen(self.var_titulo.get(), preguntas, int(self.var_cant.get() or 0),
                              int(self.var_dur.get() or 0), self.var_mp.get(), self.var_mo.get(),
                              self.var_nota.get(), self.var_bloq.get(), CARPETA_RESULTADOS)
        except (ValueError, tk.TclError) as e:
            messagebox.showerror("No se pudo iniciar", str(e))
            return
        Estado.examen = x
        self._sync_nav()
        self.btn_iniciar.configure(state="disabled")
        self.btn_cerrar.configure(state="normal")
        self.tv.delete(*self.tv.get_children())
        self.tv_ev.delete(*self.tv_ev.get_children())
        self.n_eventos = 0
        self.version_vista = -1
        self._pintar_qr()

    def _cerrar(self):
        x = Estado.examen
        if not x or not x.abierto:
            return
        activos = sum(1 for e in x.estudiantes.values() if e.activo)
        if not messagebox.askyesno("Cerrar examen",
                                   f"Se entregará automáticamente el examen de {activos} estudiante(s) en curso "
                                   "con lo que lleven contestado.\n\n¿Cerrar el examen?"):
            return
        x.cerrar()
        self.btn_iniciar.configure(state="normal")
        self.btn_cerrar.configure(state="disabled")
        self.lbl_qr.configure(image="", text="Examen cerrado.\nResultados guardados.")
        self.lbl_codigo.configure(text="")
        abrir(x.carpeta)

    def _texto_qr(self) -> str:
        x = Estado.examen
        return f"examenseguro://unirse?s={self.var_ip.get()}:{self.puerto}&c={x.codigo}"

    def _pintar_qr(self):
        x = Estado.examen
        if not x or not x.abierto:
            return
        self.qr_img = imagen_qr(self._texto_qr(), 5)
        self.lbl_qr.configure(image=self.qr_img, text="")
        self.lbl_codigo.configure(text=x.codigo)
        self.lbl_url.configure(text=f"Servidor: {self.var_ip.get()}:{self.puerto}")

    def _qr_grande(self):
        x = Estado.examen
        if not x or not x.abierto:
            return
        v = tk.Toplevel(self, bg="white")
        v.title("Escanea para entrar al examen")
        v.attributes("-fullscreen", True)
        v.bind("<Escape>", lambda e: v.destroy())
        v.bind("<Button-1>", lambda e: v.destroy())
        alto = v.winfo_screenheight()
        img = imagen_qr(self._texto_qr(), max(4, int(alto * 0.62) // 45))
        tk.Label(v, text=x.titulo, font=("Segoe UI", 30, "bold"), bg="white").pack(pady=(30, 6))
        tk.Label(v, text="Abre la app Examen Seguro, escribe tu nombre completo y escanea",
                 font=("Segoe UI", 16), bg="white", fg="#374151").pack()
        lbl = tk.Label(v, image=img, bg="white")
        lbl.image = img
        lbl.pack(expand=True)
        tk.Label(v, text=f"Código {x.codigo}   ·   {self.var_ip.get()}:{self.puerto}",
                 font=("Consolas", 22, "bold"), bg="white", fg="#1e3a8a").pack(pady=(0, 10))
        tk.Label(v, text="Esc o clic para cerrar", bg="white", fg="#9ca3af").pack(pady=(0, 16))

    def _abrir_resultados(self):
        x = Estado.examen
        ruta = x.carpeta if x else CARPETA_RESULTADOS
        os.makedirs(ruta, exist_ok=True)
        abrir(ruta)

    # ------------------------------------------------------------------ estudiantes
    def _seleccionado(self):
        sel = self.tv.selection()
        if not sel or not Estado.examen:
            messagebox.showinfo("Selecciona", "Selecciona un estudiante de la lista.")
            return None
        return sel[0]

    def _ver_detalle(self):
        token = self._seleccionado()
        if not token:
            return
        texto = Estado.examen.detalle(token)
        v = tk.Toplevel(self)
        v.title("Detalle del estudiante")
        v.geometry("900x650")
        t = tk.Text(v, wrap="word", font=("Consolas", 10), padx=10, pady=10)
        t.insert("1.0", texto)
        t.configure(state="disabled")
        t.pack(fill="both", expand=True)

    def _reingreso(self):
        token = self._seleccionado()
        if not token:
            return
        e = Estado.examen.estudiantes[token]
        if e.activo:
            messagebox.showinfo("Reingreso", "Ese estudiante sigue en el examen.")
            return
        if messagebox.askyesno("Permitir reingreso",
                               f"{e.nombre} podrá volver a escanear el QR y continuar con sus respuestas "
                               "(el tiempo sigue contando desde su inicio original).\n\n¿Autorizar?"):
            Estado.examen.permitir_reingreso(token)

    def _terminar_uno(self):
        token = self._seleccionado()
        if not token:
            return
        e = Estado.examen.estudiantes[token]
        if e.activo and messagebox.askyesno("Terminar", f"¿Terminar ahora el examen de {e.nombre}?"):
            Estado.examen.terminar_estudiante(token)

    # ------------------------------------------------------------------ refresco
    def _refrescar(self):
        try:
            x = Estado.examen
            if x:
                x.revisar_tiempos()
                self._pintar_estudiantes()
                self._pintar_eventos(False)
                err = x.guardado.error
                self.lbl_estado.configure(
                    text=f"⚠ {err}" if err else
                    (f"Guardado {x.guardado.ultimo_guardado} en {x.carpeta}" if x.guardado.ultimo_guardado else ""),
                    foreground="#b91c1c" if err else "#15803d")
        finally:
            self.after(1000, self._refrescar)

    def _pintar_estudiantes(self):
        x = Estado.examen
        filas = x.resumen()
        vistos = set()
        for f in filas:
            vals = (f["nombre"], f["estado"], f["progreso"], f["restante"], f["incidentes"],
                    f["advertencias"], f["puntaje"], f["modelo"])
            vistos.add(f["token"])
            if self.tv.exists(f["token"]):
                self.tv.item(f["token"], values=vals, tags=(f["clave"],))
            else:
                self.tv.insert("", "end", iid=f["token"], values=vals, tags=(f["clave"],))
        for iid in self.tv.get_children():
            if iid not in vistos:
                self.tv.delete(iid)
        cuenta = {}
        for e in x.estudiantes.values():
            cuenta[e.estado] = cuenta.get(e.estado, 0) + 1
        self.lbl_conteo.configure(
            text=f"«{x.titulo}» · código {x.codigo} · {'ABIERTO' if x.abierto else 'CERRADO'}   —   "
                 f"En curso {cuenta.get('activo', 0)} · Entregados {cuenta.get('entregado', 0)} · "
                 f"Terminados por salir {cuenta.get('terminado', 0)} · Tiempo agotado {cuenta.get('tiempo', 0)} · "
                 f"Total {len(x.estudiantes)}")

    def _pintar_eventos(self, todo: bool):
        x = Estado.examen
        if not x:
            return
        if todo:
            self.tv_ev.delete(*self.tv_ev.get_children())
            self.n_eventos = 0
        with x.lock:
            nuevos = x.eventos[self.n_eventos:]
            self.n_eventos = len(x.eventos)
        f = self.var_filtro.get()
        for h, nombre, tipo, det in nuevos:
            if f == "alertas" and tipo not in ("advertencia", "incidente"):
                continue
            if f == "incidente" and tipo != "incidente":
                continue
            self.tv_ev.insert("", 0, values=(h, nombre, tipo.upper(), det), tags=(tipo,))

    def _salir(self):
        x = Estado.examen
        if x and x.abierto and any(e.activo for e in x.estudiantes.values()):
            if not messagebox.askyesno("Salir", "Hay estudiantes con el examen en curso. Si sales, se cerrará el "
                                                "examen y se entregará lo que lleven.\n\n¿Salir?"):
                return
        if x and x.abierto:
            x.cerrar()
        elif x:
            x.guardado.guardar_ahora()
        self.destroy()


def main():
    if sys.platform == "win32":
        try:  # texto nítido en pantallas con escala 125 % / 150 %
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    _, puerto = servidor_red.iniciar(8765)
    Panel(puerto).mainloop()


if __name__ == "__main__":
    main()
