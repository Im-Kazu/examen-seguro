# 👩‍🏫 Guía del docente

## 1. Preparar el examen

1. Abre **`ExamenSeguroPanel.exe`** (carpeta `descargas/`).
   - Windows SmartScreen puede decir «Windows protegió su PC» porque el programa no tiene firma
     comercial: pulsa **Más información → Ejecutar de todas formas**.
   - La primera vez, Windows preguntará si el programa puede usar la red: marca **Redes privadas**
     y acepta.
2. **Cargar banco…**: elige uno o varios archivos de preguntas (`.xlsx`, `.csv` o `.txt`). Puedes
   mezclar varios bancos.
3. Configura:
   - **Título** del examen.
   - **Preguntas por alumno**: cuántas recibe cada estudiante (si el banco tiene más, se eligen al azar).
   - **Duración** en minutos.
   - **Mezclar preguntas / opciones** y **mostrar nota al final** (opcionales).

## 2. Iniciar y proyectar

1. Pulsa **▶ Iniciar examen**. Aparece un **QR** y un **código** de respaldo.
2. Usa **QR en pantalla completa** para proyectarlo. El QR y el código sirven para que los
   teléfonos se conecten a tu laptop.
3. La laptop y los teléfonos deben estar en la **misma red Wi-Fi**. Si la red de la escuela aísla
   los dispositivos entre sí, crea un **hotspot** desde tu laptop o tu teléfono y conecta ahí a
   los estudiantes.

## 3. Durante el examen

- Pestaña **Estudiantes**: estado, progreso, tiempo restante, incidentes y puntaje en vivo.
- Pestaña **Telemetría**: cada evento con su hora (conexión, salida de la app, entrega…).
- Botones: **Ver respuestas**, **Permitir reingreso**, **Terminar**.

### Si un estudiante intenta salir de la app

| Acción del estudiante | Qué pasa |
|---|---|
| Baja las notificaciones o algo tapa la app | Aviso «⚠ Estás por dejar el examen» + advertencia en el panel |
| Pulsa Atrás | Se le advierte: *Volver al examen* o *Salir y terminar* |
| Desfija la pantalla o abre la pantalla dividida | Tiene 10 s para volver; si no, el examen se termina |
| Va al escritorio, a Recientes o abre otra app | **El examen se termina**: se envían sus respuestas y el motivo |

Los exámenes terminados aparecen en rojo como **«TERMINADO (salió)»**. Si fue un error (por ejemplo
una llamada entrante), selecciona al estudiante y pulsa **Permitir reingreso**.

**Otras reglas:** un mismo nombre no puede estar en dos teléfonos; un teléfono no puede reentrar con
otro nombre; solo la app puede abrir el examen; las respuestas correctas nunca salen de tu laptop.

## 4. Cerrar y resultados

Pulsa **■ Cerrar examen**: se entrega lo que lleve cada alumno en curso y se abre la carpeta de
resultados, en `Documentos\ExamenSeguro\Resultados\<fecha>_<título>_<código>\`:

- **`resultados.xlsx`** con hojas **Resumen** (puntaje, %, calificación 0–10, incidentes, horarios,
  dispositivo), **Respuestas**, **Telemetría** y **Preguntas**.
- **`resultados.txt`**: el mismo reporte en texto plano.
- **`telemetria.txt`**: se escribe en vivo, una línea por evento.

> Si tienes `resultados.xlsx` abierto en Excel, el panel no puede sobrescribirlo y avisa: ciérralo
> y se vuelve a guardar solo.

## 5. Bancos de preguntas

Mira la plantilla en [`plantilla/Plantilla_Banco.xlsx`](../plantilla/Plantilla_Banco.xlsx) y el
ejemplo real en [`plantilla/Ejemplo_Banco_Optogenetica.xlsx`](../plantilla/Ejemplo_Banco_Optogenetica.xlsx).
El formato completo está en el [README](../README.md#-bancos-de-preguntas).

## 6. Ejecutar desde el código (opcional)

En `docente/`, con Python 3.10+: doble clic en `iniciar_panel.bat`. Para generar tu propio `.exe`,
usa `crear_exe.bat` (requiere `pip install -r requirements.txt` y PyInstaller).
