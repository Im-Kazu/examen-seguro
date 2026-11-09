# Panel del docente (código)

App de escritorio en Python + tkinter que actúa como servidor del examen en la red local.

- **Ejecutar:** `python panel_docente.py` o doble clic en `iniciar_panel.bat`. Requiere Python 3.10+
  y `pip install -r requirements.txt` (openpyxl, segno).
- **Generar el .exe:** `crear_exe.bat` (usa PyInstaller, modo un solo archivo y sin consola).

Archivos: `nucleo.py` (modelo de examen, carga de bancos, calificación y guardado),
`servidor_red.py` (servidor HTTP y rutas), `panel_docente.py` (interfaz y QR), `web/examen.html`
(página del examen que ven los teléfonos).

> El `.exe` ya compilado está en [`../descargas/ExamenSeguroPanel.exe`](../descargas/ExamenSeguroPanel.exe).
