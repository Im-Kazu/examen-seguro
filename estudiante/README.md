# App del estudiante (código)

Navegador seguro para Android (Kotlin + WebView) que bloquea la salida del examen.

- **Abrir:** Android Studio → *File → Open* → esta carpeta `estudiante/`.
- **APK de depuración:** `./gradlew assembleDebug`.
- **APK de release firmado y ofuscado:** `./gradlew assembleRelease`. Necesita un archivo
  `keystore.properties` en esta carpeta (no se incluye por seguridad) con:

  ```properties
  storeFile=examenseguro.jks
  storePassword=TU_CONTRASEÑA
  keyAlias=examenseguro
  keyPassword=TU_CONTRASEÑA
  ```

  y la llave `examenseguro.jks` correspondiente. Crea una con:

  ```bash
  keytool -genkeypair -v -keystore examenseguro.jks -alias examenseguro \
    -keyalg RSA -keysize 2048 -validity 10000
  ```

El release usa **R8** (ofuscación, eliminación de código y recursos no usados); las reglas están en
`app/proguard-rules.pro`. Requiere **JDK 17** y **Android SDK 35**, **minSdk 26** (Android 8.0).

> El APK ya compilado (release firmado) está en [`../descargas/ExamenSeguro.apk`](../descargas/ExamenSeguro.apk).
