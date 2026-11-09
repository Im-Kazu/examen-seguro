# 🛡️ Examen Seguro

Sistema para aplicar exámenes en el aula con el teléfono de cada estudiante, sin que puedan
salir de la app ni consultar nada más. La **laptop del docente** funciona como servidor: genera
un QR, los estudiantes lo escanean y responden desde sus teléfonos **Android**. Si alguien
intenta salir del examen, se le avisa y, si insiste, el examen se da por terminado y queda
registrado.

Todo el examen viaja por la **red local** (Wi-Fi del aula o un hotspot). Las respuestas correctas
nunca salen de la laptop, y los resultados se guardan en tu PC como **Excel** y **texto**.

---

## ⬇️ Descargas (ya compiladas)

| Para | Archivo | Requisito |
|---|---|---|
| 👩‍🏫 **Docente** | [`descargas/ExamenSeguroPanel.exe`](descargas/ExamenSeguroPanel.exe) | Windows 10/11 |
| 🧑‍🎓 **Estudiante** | [`descargas/ExamenSeguro.apk`](descargas/ExamenSeguro.apk) | Android 8.0 o superior |

> También están publicadas en la pestaña **[Releases](../../releases/latest)**, con enlaces
> estables para compartir con el grupo.

El `.exe` no necesita instalación. El `.apk` se instala en el teléfono permitiendo «Instalar apps
desconocidas». Ninguno pide permisos especiales de cámara, contactos ni archivos.

---

## 🚀 Uso en 6 pasos

1. El docente abre **`ExamenSeguroPanel.exe`**.
2. **Cargar banco…** → elige tu archivo de preguntas (Excel, CSV o TXT). Pon título, cuántas
   preguntas recibe cada alumno y la duración.
3. **▶ Iniciar examen** → aparece un **QR** (hay botón de pantalla completa para el proyector).
4. Cada estudiante abre **Examen Seguro**, escribe su **nombre completo** y **escanea el QR**.
5. El docente ve en vivo el estado, el progreso, el tiempo y los incidentes de cada alumno.
6. **■ Cerrar examen** → se guardan los resultados y se abre la carpeta.

La laptop y los teléfonos deben estar en la **misma red Wi-Fi**. Si la red de la escuela aísla los
dispositivos, usa el **hotspot** de tu laptop o teléfono.

📖 Guías completas: **[Guía del docente](docs/GUIA_DOCENTE.md)** · **[Guía del estudiante](docs/GUIA_ESTUDIANTE.md)**

---

## 📝 Bancos de preguntas

Usa la **plantilla de Excel** ya lista:

- **[`plantilla/Plantilla_Banco.xlsx`](plantilla/Plantilla_Banco.xlsx)** — con ejemplos de cada tipo.
- **[`plantilla/Ejemplo_Banco_Optogenetica.xlsx`](plantilla/Ejemplo_Banco_Optogenetica.xlsx)** — un banco real de 26 preguntas.

El panel también tiene un botón **Plantilla Excel** que la genera. Columnas:

| Pregunta | Tipo | A | B | C | D | E | Correcta | Puntos |
|---|---|---|---|---|---|---|---|---|
| ¿Capital de Francia? | opcion | Madrid | París | Roma | Berlín | | B | 1 |
| Números primos | multiple | 2 | 4 | 7 | 9 | | A,C | 2 |
| El agua hierve a 100 °C | vf | | | | | | V | 1 |
| ¿Autor del Quijote? | abierta | | | | | | Cervantes\|Miguel de Cervantes | 1 |

- **opcion**: una sola respuesta correcta. **multiple**: varias (sepáralas con comas en *Correcta*).
- **vf**: verdadero/falso (pon `V` o `F` en *Correcta*).
- **abierta**: respuesta escrita; acepta varias respuestas válidas separadas por `|`. Si dejas
  *Correcta* vacío, se revisa a mano. No distingue acentos ni mayúsculas.

También acepta **CSV** y **TXT en formato Aiken** (el de Moodle).

---

## 🔒 Qué protege

**En el teléfono del estudiante:**
- Pantalla fijada (screen pinning), pantalla completa y sin pantalla dividida.
- Sin capturas ni grabación de pantalla, y sin vista previa en «Recientes».
- Solo se puede navegar al servidor del docente.
- No se puede copiar, pegar ni seleccionar texto; el portapapeles se vacía.
- Si el estudiante sale de la app (Inicio, Recientes u otra app), **el examen se termina** y el
  docente lo ve en vivo.

**En la aplicación (contra copia del código):**
- El APK se compila en **release firmado**, con **R8**: ofusca los nombres de clases y métodos,
  elimina el código y los recursos no usados y borra los mensajes de registro.
- El panel se distribuye como **ejecutable compilado** (no se incluye el código fuente `.py` en
  el `.exe`).
- Las **respuestas correctas nunca se envían al teléfono**: se califican solo en la laptop.

> Ninguna ofuscación es irreversible: dificulta mucho el análisis, pero no es un blindaje
> absoluto. Sirve para desalentar la copia casual del código.

---

## 📂 Contenido del repositorio

```
examen-seguro/
├─ descargas/     ← el .exe y el .apk ya compilados
├─ plantilla/     ← plantilla de Excel y un banco de ejemplo
├─ docente/       ← código del panel (Python)
├─ estudiante/    ← código de la app Android (Kotlin)
└─ docs/          ← guías de uso
```

Para compilar desde el código, mira **[docente/](docente/)** (Python 3.10+) y
**[estudiante/](estudiante/)** (Android Studio o `./gradlew assembleRelease`).

---

## ⚠️ Límites

- No impide que el estudiante use **otro dispositivo** ni apuntes físicos.
- La red local es **HTTP sin cifrar**: úsalo en la red del aula, no en redes públicas.
- Una **llamada entrante** saca al estudiante de la app. Pide modo avión con Wi-Fi activado o «No molestar».
- **iPhone no es compatible** (Apple obliga a usar WebKit y no permite este tipo de bloqueo).
