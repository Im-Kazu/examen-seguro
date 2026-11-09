package com.examenseguro.navegador

import android.annotation.SuppressLint
import android.app.ActivityManager
import android.app.admin.DevicePolicyManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.res.Configuration
import android.graphics.Bitmap
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.view.KeyEvent
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.GeolocationPermissions
import android.webkit.JsPromptResult
import android.webkit.JsResult
import android.webkit.PermissionRequest
import android.webkit.RenderProcessGoneDetail
import android.webkit.SslErrorHandler
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebStorage
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.Chronometer
import android.widget.FrameLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.core.view.isVisible
import androidx.webkit.WebSettingsCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Pantalla del examen: WebView (Chromium del sistema) en modo bloqueado.
 *
 * Dos modos:
 *  - RED LOCAL (QR del panel del docente): el examen lo sirve la computadora del docente.
 *    Si el estudiante intenta salir se le ADVIERTE; si sale de todas formas, el examen se
 *    TERMINA y se avisa al panel con el motivo.
 *  - WEB (URL configurada en el teléfono): Google Forms, Moodle, etc. Solo registra incidentes
 *    y se sale con el PIN del docente.
 *
 * Protecciones comunes: FLAG_SECURE (sin capturas/grabación), fijación de pantalla o kiosco,
 * pantalla completa, lista blanca de sitios, sin copiar/pegar/descargar/subir, portapapeles
 * vaciado, sesión limpia y registro de incidentes.
 */
class ExamActivity : AppCompatActivity() {

    private lateinit var config: ExamConfig
    private lateinit var webContainer: FrameLayout
    private var webView: WebView? = null
    private lateinit var gate: View
    private lateinit var gateTitle: TextView
    private lateinit var gateMsg: TextView
    private lateinit var gateMain: Button
    private lateinit var gateCancel: Button
    private lateinit var shield: View
    private lateinit var shieldTitle: TextView
    private lateinit var shieldMsg: TextView
    private lateinit var tvIncidents: TextView
    private lateinit var btnFinish: Button
    private lateinit var timer: Chronometer
    private lateinit var progress: ProgressBar
    private lateinit var clipboard: ClipboardManager

    // Modo red local
    private var lanServer: String? = null
    private var lanToken: String? = null
    private val isLan get() = lanToken != null

    private var requireLock = true
    private var startUrl = ""
    private var studentName = ""

    private val handler = Handler(Looper.getMainLooper())
    private var examStarted = false
    private var exiting = false       // salida normal (PIN o entrega)
    private var terminated = false    // terminado por salir de la app (modo red local)
    private var ownDialogOpen = false
    private var lockLost = false
    private var graceReason: String? = null
    private var graceLeft = 0
    private var gateAction: () -> Unit = {}
    private var incidentCount = 0
    private val lastIncidentAt = HashMap<String, Long>()
    private val clock = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    private val clipListener = ClipboardManager.OnPrimaryClipChangedListener {
        if (active()) clearClipboard()
    }

    private fun active() = examStarted && !exiting && !terminated

    // ------------------------------------------------------------------ ciclo de vida

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) window.setHideOverlayWindows(true)

        setContentView(R.layout.activity_exam)
        config = ExamConfig(this)
        clipboard = getSystemService(ClipboardManager::class.java)

        lanServer = intent.getStringExtra(EXTRA_SERVER)
        lanToken = intent.getStringExtra(EXTRA_TOKEN)
        if (isLan) {
            requireLock = intent.getBooleanExtra(EXTRA_REQUIRE_LOCK, true)
            startUrl = intent.getStringExtra(EXTRA_URL).orEmpty()
            studentName = intent.getStringExtra(EXTRA_NAME).orEmpty()
        } else {
            requireLock = config.requireLock
            startUrl = config.examUrl
            studentName = config.studentName
        }

        findViewById<View>(R.id.root).applySystemInsets()
        webContainer = findViewById(R.id.webContainer)
        gate = findViewById(R.id.gate)
        gateTitle = findViewById(R.id.tvGateTitle)
        gateMsg = findViewById(R.id.tvGateMsg)
        gateMain = findViewById(R.id.btnGateRetry)
        gateCancel = findViewById(R.id.btnGateCancel)
        shield = findViewById(R.id.shield)
        shieldTitle = findViewById(R.id.tvShieldTitle)
        shieldMsg = findViewById(R.id.tvShieldMsg)
        tvIncidents = findViewById(R.id.tvIncidents)
        btnFinish = findViewById(R.id.btnFinish)
        timer = findViewById(R.id.timer)
        progress = findViewById(R.id.progress)
        findViewById<TextView>(R.id.tvStudent).text = studentName

        // En red local se entrega desde la propia página del examen.
        btnFinish.isVisible = !isLan
        btnFinish.setOnClickListener { askPinToExit() }
        findViewById<Button>(R.id.btnReload).setOnClickListener { if (active()) webView?.reload() }
        gateMain.setOnClickListener { gateAction() }
        gateCancel.setOnClickListener { if (!examStarted) finish() }
        shield.setOnClickListener { if (hasWindowFocus()) shield.isVisible = false }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                when {
                    !examStarted || exiting || terminated -> finish()
                    else -> warnLeaving()
                }
            }
        })

        clipboard.addPrimaryClipChangedListener(clipListener)
        hideSystemBars()
        wipeBrowsingData()
        createWebView()

        if (savedInstanceState == null) {
            config.clearIncidents()
            config.lastReportHeader = ""
        } else {
            registerIncident("La app fue reiniciada por el sistema durante el examen")
        }

        if (requireLock) {
            showLockGate()
            enterLockTask()
        } else {
            startExam()
        }
        handler.post(watcher)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) {
            hideSystemBars()
            if (!isInMultiWindowMode && graceReason == null) shield.isVisible = false
            if (active()) clearClipboard()
        } else if (active() && !ownDialogOpen) {
            // Primer paso de casi cualquier salida: bajar notificaciones, abrir otra app, etc.
            showShield(
                "⚠ Estás por dejar el examen",
                if (isLan) "Si sales de esta app, tu examen se TERMINARÁ y se avisará al docente.\nToca aquí para seguir con el examen."
                else "Este evento quedó registrado. Toca aquí para seguir con el examen."
            )
            registerWarning("La app perdió el foco (notificaciones, diálogo o intento de cambiar de app)")
        }
    }

    override fun onUserLeaveHint() {
        super.onUserLeaveHint()
        if (active()) leftTheApp("Salió de la app con el botón Inicio o Recientes")
    }

    override fun onStop() {
        super.onStop()
        if (active() && !isChangingConfigurations) {
            val screenOn = getSystemService(PowerManager::class.java)?.isInteractive != false
            if (screenOn) leftTheApp("La app pasó a segundo plano (abrió otra app)")
            else registerWarning("Se apagó la pantalla")
        }
    }

    override fun onResume() {
        super.onResume()
        if (isInMultiWindowMode) shield.isVisible = true
        hideSystemBars()
    }

    override fun onMultiWindowModeChanged(isInMultiWindowMode: Boolean, newConfig: Configuration) {
        super.onMultiWindowModeChanged(isInMultiWindowMode, newConfig)
        if (isInMultiWindowMode && active()) {
            showShield("⚠ Pantalla dividida no permitida", "Vuelve a pantalla completa para continuar.")
            if (!isLan) registerIncident("Intentó usar pantalla dividida / ventana flotante")
            // En red local el vigilante inicia la cuenta regresiva.
        } else if (!isInMultiWindowMode && graceReason == null) {
            shield.isVisible = false
        }
    }

    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        // Teclado físico: bloquea atajos de copiar/pegar/imprimir/guardar/cambiar de app.
        if (event.isCtrlPressed || event.isMetaPressed || event.isAltPressed) {
            when (event.keyCode) {
                KeyEvent.KEYCODE_C, KeyEvent.KEYCODE_V, KeyEvent.KEYCODE_X, KeyEvent.KEYCODE_A,
                KeyEvent.KEYCODE_P, KeyEvent.KEYCODE_S, KeyEvent.KEYCODE_TAB -> return true
            }
        }
        if (event.keyCode == KeyEvent.KEYCODE_SEARCH || event.keyCode == KeyEvent.KEYCODE_ASSIST) return true
        return super.dispatchKeyEvent(event)
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        clipboard.removePrimaryClipChangedListener(clipListener)
        webView?.let { it.stopLoading(); it.destroy() }
        webView = null
        super.onDestroy()
    }

    // ------------------------------------------------------------------ advertir / terminar

    /** Botón Atrás (o el primer intento de desfijar): advertencia explícita. */
    private fun warnLeaving() {
        registerWarning("Pulsó Atrás / intentó salir del examen")
        ownDialogOpen = true
        val b = MaterialAlertDialogBuilder(this)
            .setTitle("⚠ Estás por dejar el examen")
            .setOnDismissListener { ownDialogOpen = false; hideSystemBars() }
        if (isLan) {
            b.setMessage("Si sales ahora, tu examen se dará por TERMINADO con las respuestas que llevas, " +
                "y el docente verá que saliste.\n\nPara entregar normalmente usa el botón «Entregar examen».")
                .setPositiveButton("Volver al examen", null)
                .setNegativeButton("Salir y terminar") { _, _ -> terminate("Decidió salir del examen (botón Atrás)") }
        } else {
            b.setMessage("No puedes salir hasta que el docente escriba su PIN. Este intento quedó registrado.")
                .setPositiveButton("Volver al examen", null)
        }
        b.show()
    }

    /** El estudiante realmente salió de la app. */
    private fun leftTheApp(reason: String) {
        if (isLan) terminate(reason) else registerIncident(reason)
    }

    /** Fin del examen por salir de la app (modo red local). */
    private fun terminate(reason: String) {
        if (terminated || exiting || !isLan) return
        terminated = true
        registerIncident("EXAMEN TERMINADO: $reason")
        LanClient.terminate(lanServer!!, lanToken!!, reason)
        graceReason = null
        timer.stop()
        webView?.loadUrl("about:blank")
        wipeBrowsingData()
        runCatching { stopLockTask() }
        shield.isVisible = false
        showGate(
            title = "⛔ Examen terminado",
            message = "Saliste del examen: $reason.\n\nSe registró y tu examen se envió al docente con las " +
                "respuestas que llevabas. Si fue un error, habla con tu docente.",
            button = "Cerrar",
            cancellable = false,
        ) { finish() }
    }

    /** Cuenta regresiva cuando se desfija la pantalla o entra en pantalla dividida (red local). */
    private fun startGrace(reason: String) {
        if (graceReason != null || !active()) return
        graceReason = reason
        graceLeft = GRACE_SECONDS
        registerWarning("$reason — cuenta regresiva de $GRACE_SECONDS s")
        handler.post(graceTick)
    }

    private val graceTick = object : Runnable {
        override fun run() {
            val reason = graceReason ?: return
            if (!active()) return
            if (graceLeft <= 0) {
                terminate(reason)
                return
            }
            showGate(
                title = "⚠ Estás por dejar el examen",
                message = "$reason.\n\nVuelve a fijar la pantalla en $graceLeft s o tu examen se TERMINARÁ.",
                button = "Volver al examen",
                cancellable = false,
            ) { enterLockTask() }
            graceLeft--
            handler.postDelayed(this, 1000)
        }
    }

    private fun cancelGrace() {
        if (graceReason == null) return
        graceReason = null
        handler.removeCallbacks(graceTick)
        gate.isVisible = false
        shield.isVisible = false
        registerInfo("Volvió al examen a tiempo")
    }

    // ------------------------------------------------------------------ fijación de pantalla

    private fun enterLockTask() {
        val dpm = getSystemService(DevicePolicyManager::class.java)
        if (dpm != null && dpm.isDeviceOwnerApp(packageName)) {
            // Kiosco total: sin barra de estado, sin notificaciones, sin Inicio/Recientes y sin confirmación.
            val admin = ComponentName(this, AdminReceiver::class.java)
            dpm.setLockTaskPackages(admin, arrayOf(packageName))
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                dpm.setLockTaskFeatures(admin, DevicePolicyManager.LOCK_TASK_FEATURE_NONE)
            }
        }
        runCatching { startLockTask() }
            .onFailure { gateMsg.text = "No se pudo fijar la pantalla: ${it.message}" }
    }

    private fun isLocked(): Boolean =
        getSystemService(ActivityManager::class.java).lockTaskModeState != ActivityManager.LOCK_TASK_MODE_NONE

    /** Vigila continuamente la fijación de pantalla y la multiventana. */
    private val watcher = object : Runnable {
        override fun run() {
            if (exiting || terminated) return
            val locked = !requireLock || isLocked()
            when {
                !examStarted && locked && requireLock -> startExam()
                examStarted && isLan -> {
                    val problem = when {
                        !locked -> "Se desactivó la fijación de pantalla"
                        isInMultiWindowMode -> "Abrió pantalla dividida / ventana flotante"
                        else -> null
                    }
                    if (problem != null) startGrace(problem) else cancelGrace()
                }
                examStarted && !locked && !lockLost -> {
                    lockLost = true
                    registerIncident("Se desactivó la fijación de pantalla")
                    showGate(
                        "Examen bloqueado",
                        "Se desactivó la fijación de pantalla. Este evento quedó registrado.\n" +
                            "Pulsa el botón para volver a fijarla y continuar.",
                        "Fijar pantalla", false,
                    ) { enterLockTask() }
                }
                examStarted && locked && lockLost -> {
                    lockLost = false
                    gate.isVisible = false
                }
            }
            handler.postDelayed(this, 700)
        }
    }

    private fun showLockGate() = showGate(
        "Preparando examen seguro",
        "Android te pedirá «Fijar app». Acepta para comenzar.\n" +
            "Mientras dure el examen no podrás salir de esta pantalla." +
            if (isLan) "\n\nSi sales de la app, tu examen se terminará." else "",
        "Fijar pantalla y comenzar", true,
    ) { enterLockTask() }

    private fun showGate(title: String, message: String, button: String, cancellable: Boolean, action: () -> Unit) {
        gate.isVisible = true
        gateTitle.text = title
        gateMsg.text = message
        gateMain.text = button
        gateCancel.isVisible = cancellable
        gateAction = action
    }

    private fun showShield(title: String, message: String) {
        shieldTitle.text = title
        shieldMsg.text = message
        shield.isVisible = true
    }

    private fun startExam() {
        if (examStarted) return
        examStarted = true
        gate.isVisible = false
        clearClipboard()
        timer.base = SystemClock.elapsedRealtime()
        timer.start()
        DeviceChecks.warnings(this).forEach { send("aviso", "Aviso del dispositivo: $it"); logLocal("Aviso: $it") }
        if (isLan) send("info", "Abrió el examen en modo seguro" + if (requireLock) " (pantalla fijada)" else "")
        config.lastReportHeader = "Estudiante: $studentName · Inicio: ${clock.format(Date())}"
        webView?.loadUrl(startUrl)
    }

    // ------------------------------------------------------------------ WebView

    private fun isAllowed(uri: Uri): Boolean {
        if (!isLan) return config.isAllowed(uri)
        if (uri.toString() == "about:blank") return true
        val s = Uri.parse(lanServer)
        return uri.scheme == s.scheme && uri.host == s.host && uri.port == s.port
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun createWebView() {
        WebView.setWebContentsDebuggingEnabled(false)
        val wv = WebView(this)
        webContainer.removeAllViews()
        webContainer.addView(wv, FrameLayout.LayoutParams(-1, -1))
        webView = wv

        wv.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            setSupportMultipleWindows(false)
            javaScriptCanOpenWindowsAutomatically = false
            setGeolocationEnabled(false)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            mediaPlaybackRequiresUserGesture = true
            builtInZoomControls = true
            displayZoomControls = false
            userAgentString = "$userAgentString $USER_AGENT_SUFFIX"
        }
        if (WebViewFeature.isFeatureSupported(WebViewFeature.SAFE_BROWSING_ENABLE)) {
            WebSettingsCompat.setSafeBrowsingEnabled(wv.settings, true)
        }
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(wv, true) // inicios de sesión de Google/Microsoft en modo web
        }

        wv.isLongClickable = false
        wv.isHapticFeedbackEnabled = false
        wv.setOnLongClickListener { true }
        wv.setDownloadListener { url, _, _, _, _ ->
            registerIncident("Descarga bloqueada: ${Uri.parse(url).host}")
            toast("Las descargas están bloqueadas durante el examen")
        }

        val docStart = WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)
        if (docStart) WebViewCompat.addDocumentStartJavaScript(wv, GuardScript.SOURCE, setOf("*"))

        wv.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri = request.url
                if (isAllowed(uri)) return false
                val target = uri.host ?: uri.scheme ?: uri.toString()
                registerIncident("Intentó abrir un sitio no permitido: $target")
                toast("Sitio bloqueado: $target")
                return true
            }

            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                progress.isVisible = true
                // La página del docente navega a /fin al entregar, al agotarse el tiempo o al cerrar el examen.
                if (isLan && url != null && Uri.parse(url).path?.startsWith("/fin") == true) examDelivered()
            }

            override fun onPageFinished(view: WebView, url: String?) {
                progress.isVisible = false
                if (!docStart) view.evaluateJavascript(GuardScript.SOURCE, null)
            }

            override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
                handler.cancel() // nunca aceptar certificados inválidos
                registerIncident("Certificado HTTPS inválido en ${Uri.parse(error.url).host}")
                toast("Conexión no segura bloqueada")
            }

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                registerIncident("El motor del navegador se reinició")
                webContainer.removeAllViews()
                view.destroy()
                createWebView()
                if (examStarted && !terminated) webView?.loadUrl(startUrl)
                return true
            }
        }

        wv.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, newProgress: Int) {
                progress.progress = newProgress
            }

            override fun onPermissionRequest(request: PermissionRequest) = request.deny()

            override fun onGeolocationPermissionsShowPrompt(
                origin: String, callback: GeolocationPermissions.Callback
            ) = callback.invoke(origin, false, false)

            override fun onShowFileChooser(
                webView: WebView,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams
            ): Boolean {
                filePathCallback.onReceiveValue(null)
                toast("Subir archivos está bloqueado durante el examen")
                return true
            }

            // Los diálogos JS de la página se muestran como propios (no cuentan como "salir").
            override fun onJsAlert(view: WebView, url: String?, message: String?, result: JsResult): Boolean {
                pageDialog(message, result, confirm = false); return true
            }

            override fun onJsConfirm(view: WebView, url: String?, message: String?, result: JsResult): Boolean {
                pageDialog(message, result, confirm = true); return true
            }

            override fun onJsPrompt(
                view: WebView, url: String?, message: String?, defaultValue: String?, result: JsPromptResult
            ): Boolean {
                result.cancel(); return true
            }
        }
    }

    private fun pageDialog(message: String?, result: JsResult, confirm: Boolean) {
        ownDialogOpen = true
        val b = MaterialAlertDialogBuilder(this)
            .setMessage(message.orEmpty())
            .setCancelable(false)
            .setPositiveButton("Aceptar") { _, _ -> result.confirm() }
            .setOnDismissListener { ownDialogOpen = false; hideSystemBars() }
        if (confirm) b.setNegativeButton("Cancelar") { _, _ -> result.cancel() }
        b.show()
    }

    private fun wipeBrowsingData() {
        CookieManager.getInstance().removeAllCookies(null)
        CookieManager.getInstance().flush()
        WebStorage.getInstance().deleteAllData()
        webView?.apply { clearCache(true); clearHistory(); clearFormData() }
    }

    // ------------------------------------------------------------------ registro / telemetría

    private fun logLocal(line: String) {
        config.appendIncident("${clock.format(Date())} — $line")
    }

    private fun debounced(reason: String): Boolean {
        val now = SystemClock.elapsedRealtime()
        val prev = lastIncidentAt[reason]
        if (prev != null && now - prev < 2000) return true
        lastIncidentAt[reason] = now
        return false
    }

    /** Envía al panel del docente (solo modo red local). */
    private fun send(type: String, detail: String) {
        val s = lanServer
        val t = lanToken
        if (s != null && t != null) LanClient.telemetry(s, t, type, detail)
    }

    private fun registerIncident(reason: String) {
        if (debounced(reason)) return
        incidentCount++
        logLocal(reason)
        if (::tvIncidents.isInitialized) tvIncidents.text = "⚠ $incidentCount"
        if (!reason.startsWith("EXAMEN TERMINADO")) send("incidente", reason) // el fin lo registra /api/terminar
        notifyPage(reason)
    }

    private fun registerWarning(reason: String) {
        if (debounced(reason)) return
        logLocal("Advertencia: $reason")
        send("advertencia", reason)
        notifyPage(reason)
    }

    private fun registerInfo(reason: String) {
        logLocal(reason)
        send("info", reason)
    }

    private fun notifyPage(reason: String) {
        // La página del examen puede escuchar: window.addEventListener('examenseguro:incidente', ...)
        webView?.evaluateJavascript(
            "window.dispatchEvent(new CustomEvent('examenseguro:incidente',{detail:${JSONObject.quote(reason)}}));",
            null
        )
    }

    // ------------------------------------------------------------------ utilidades

    private fun hideSystemBars() {
        val controller = WindowCompat.getInsetsController(window, window.decorView)
        controller.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        controller.hide(WindowInsetsCompat.Type.systemBars())
    }

    private fun clearClipboard() {
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                if (clipboard.hasPrimaryClip()) clipboard.clearPrimaryClip()
            } else {
                val text = clipboard.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.text
                if (!text.isNullOrEmpty()) clipboard.setPrimaryClip(ClipData.newPlainText("", ""))
            }
        }
    }

    // ------------------------------------------------------------------ salida normal

    /** Modo red local: la página llegó a /fin (entregado, tiempo agotado o cerrado por el docente). */
    private fun examDelivered() {
        if (exiting || terminated) return
        exiting = true
        graceReason = null
        handler.removeCallbacksAndMessages(null)
        timer.stop()
        runCatching { stopLockTask() }
        clearClipboard()
        gate.isVisible = false
        shield.isVisible = false
        btnFinish.text = "Cerrar"
        btnFinish.isVisible = true
        btnFinish.setOnClickListener { wipeBrowsingData(); finish() }
    }

    /** Modo web: salir solo con el PIN del docente. */
    private fun askPinToExit() {
        if (!examStarted) { finish(); return }
        ownDialogOpen = true
        PinDialog.show(
            activity = this,
            config = config,
            title = "Finalizar examen",
            message = "Asegúrate de haber ENVIADO tus respuestas.\nSolo el docente puede cerrar el examen.",
            onDismiss = { ownDialogOpen = false; hideSystemBars() },
            onWrong = { registerIncident("PIN incorrecto al intentar salir") },
            onOk = { finishWebExam() },
        )
    }

    private fun finishWebExam() {
        exiting = true
        examStarted = false
        timer.stop()
        handler.removeCallbacksAndMessages(null)
        val minutes = (SystemClock.elapsedRealtime() - timer.base) / 60_000
        runCatching { stopLockTask() }
        clearClipboard()
        wipeBrowsingData()
        webView?.loadUrl("about:blank")

        val list = config.incidents()
        config.lastReportHeader += " · Duración: $minutes min · Incidentes: ${list.size}"
        MaterialAlertDialogBuilder(this)
            .setTitle("Examen finalizado")
            .setMessage(
                "${config.lastReportHeader}\n\n" +
                    (if (list.isEmpty()) "Sin incidentes." else list.joinToString("\n"))
            )
            .setCancelable(false)
            .setPositiveButton("Cerrar") { _, _ -> finish() }
            .show()
    }

    companion object {
        /** El servidor del examen puede verificar este sufijo en el User-Agent. */
        const val USER_AGENT_SUFFIX = "ExamenSeguro/1.0"
        const val EXTRA_SERVER = "server"
        const val EXTRA_TOKEN = "token"
        const val EXTRA_URL = "url"
        const val EXTRA_NAME = "name"
        const val EXTRA_REQUIRE_LOCK = "require_lock"
        private const val GRACE_SECONDS = 10
    }
}
