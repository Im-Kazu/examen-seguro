package com.examenseguro.navegador

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import android.view.WindowManager
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.TextView
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.textfield.TextInputEditText

/** Pantalla inicial: el estudiante escribe su nombre y comienza; el docente configura con PIN. */
class ConfigActivity : AppCompatActivity() {

    private lateinit var config: ExamConfig
    private lateinit var etStudent: TextInputEditText
    private lateinit var etUrl: TextInputEditText
    private lateinit var etDomains: TextInputEditText
    private lateinit var etPin: TextInputEditText
    private lateinit var etPin2: TextInputEditText
    private lateinit var swLock: MaterialSwitch
    private lateinit var btnUnlock: Button
    private lateinit var btnSave: Button
    private lateinit var btnReport: Button
    private lateinit var tvWarnings: TextView
    private lateinit var tvTeacherState: TextView
    private lateinit var tvExamInfo: TextView

    private var unlocked = false
    private var pendingLink: Uri? = null
    private var pendingJoin: LanInfo? = null
    private var joining = false
    private lateinit var btnScan: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        setContentView(R.layout.activity_config)
        findViewById<View>(R.id.root).applySystemInsets()
        config = ExamConfig(this)

        etStudent = findViewById(R.id.etStudent)
        etUrl = findViewById(R.id.etUrl)
        etDomains = findViewById(R.id.etDomains)
        etPin = findViewById(R.id.etPin)
        etPin2 = findViewById(R.id.etPin2)
        swLock = findViewById(R.id.swLock)
        btnUnlock = findViewById(R.id.btnUnlock)
        btnSave = findViewById(R.id.btnSave)
        btnReport = findViewById(R.id.btnReport)
        tvWarnings = findViewById(R.id.tvWarnings)
        tvTeacherState = findViewById(R.id.tvTeacherState)
        tvExamInfo = findViewById(R.id.tvExamInfo)

        etStudent.setText(config.studentName)
        loadTeacherFields()

        btnScan = findViewById(R.id.btnScan)
        btnScan.setOnClickListener { scanQr() }
        findViewById<Button>(R.id.btnManual).setOnClickListener { manualCode() }
        findViewById<Button>(R.id.btnStart).setOnClickListener { startExam() }
        btnUnlock.setOnClickListener { toggleUnlock() }
        btnSave.setOnClickListener { save() }
        btnReport.setOnClickListener { showReport() }

        handleDeepLink(intent)
        refreshState()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleDeepLink(intent)
    }

    override fun onResume() {
        super.onResume()
        refreshState()
    }

    private fun teacherEditable() = unlocked || !config.hasPin()

    private fun loadTeacherFields() {
        etUrl.setText(config.examUrl)
        etDomains.setText(config.extraHosts.joinToString(", "))
        swLock.isChecked = config.requireLock
        etPin.text = null
        etPin2.text = null
    }

    private fun refreshState() {
        val editable = teacherEditable()
        listOf<View>(etUrl, etDomains, etPin, etPin2, swLock, btnSave).forEach { it.isEnabled = editable }
        btnUnlock.isVisible = config.hasPin()
        btnUnlock.text = if (unlocked) "Bloquear configuración" else "Desbloquear con PIN"
        tvTeacherState.text = when {
            !config.hasPin() -> "Primera vez: define la URL del examen y un PIN de docente."
            unlocked -> "Configuración desbloqueada. Guarda para volver a protegerla."
            else -> "Configuración protegida con PIN."
        }

        tvExamInfo.text = "Escribe tu nombre completo y escanea el QR que muestra tu docente." +
            if (config.examUrl.isBlank()) "" else "\nExamen web configurado: ${Uri.parse(config.examUrl).host}"
        findViewById<Button>(R.id.btnStart).isVisible = config.examUrl.isNotBlank()

        val lines = mutableListOf<String>()
        lines += if (DeviceChecks.isDeviceOwner(this)) "✔ Modo kiosco total disponible (propietario del dispositivo)"
        else "ℹ Se usará «Fijar app» de Android"
        DeviceChecks.warnings(this).forEach { lines += "⚠ $it" }
        tvWarnings.text = lines.joinToString("\n")

        val n = config.incidents().size
        btnReport.isVisible = config.lastReportHeader.isNotBlank()
        btnReport.text = "Ver reporte del último examen ($n incidentes)"
    }

    private fun toggleUnlock() {
        if (unlocked) {
            unlocked = false
            loadTeacherFields()
            refreshState()
            return
        }
        PinDialog.show(this, config, "Configuración del docente", "Introduce el PIN para editar.") {
            unlocked = true
            pendingLink?.let { applyLink(it) }
            pendingLink = null
            refreshState()
        }
    }

    private fun save() {
        val url = etUrl.text?.toString()?.trim().orEmpty()
        val uri = Uri.parse(url)
        if (uri.scheme != "https" || uri.host.isNullOrBlank()) {
            etUrl.error = "Debe ser una URL válida que empiece con https://"
            return
        }
        val pin = etPin.text?.toString().orEmpty()
        val pin2 = etPin2.text?.toString().orEmpty()
        if (!config.hasPin() && pin.isEmpty()) {
            etPin.error = "Define un PIN de docente"
            return
        }
        if (pin.isNotEmpty()) {
            if (pin.length < 4) { etPin.error = "Mínimo 4 dígitos"; return }
            if (pin != pin2) { etPin2.error = "Los PIN no coinciden"; return }
            config.setPin(pin)
        }
        config.examUrl = url
        config.extraHosts = ExamConfig.parseHosts(etDomains.text?.toString().orEmpty())
        config.requireLock = swLock.isChecked

        unlocked = false
        loadTeacherFields()
        refreshState()
        hideKeyboard()
        toast("Configuración guardada")
    }

    private fun startExam() {
        if (config.examUrl.isBlank() || !config.hasPin()) {
            toast("El docente debe configurar el examen y su PIN primero")
            return
        }
        val name = etStudent.text?.toString()?.trim().orEmpty()
        if (name.length < 3) {
            etStudent.error = "Escribe tu nombre completo"
            return
        }
        config.studentName = name
        unlocked = false
        loadTeacherFields()
        hideKeyboard()
        startActivity(Intent(this, ExamActivity::class.java))
    }

    private fun showReport() {
        val list = config.incidents()
        MaterialAlertDialogBuilder(this)
            .setTitle("Reporte del último examen")
            .setMessage(
                "${config.lastReportHeader}\n\n" +
                    (if (list.isEmpty()) "Sin incidentes." else list.joinToString("\n"))
            )
            .setPositiveButton("Cerrar", null)
            .show()
    }

    // ------------------------------------------------------------------ examen en red local (QR)

    private fun studentNameOrError(): String? {
        val name = etStudent.text?.toString()?.trim()?.replace(Regex("\\s+"), " ").orEmpty()
        if (name.length < 5 || !name.contains(' ')) {
            etStudent.error = "Escribe tu nombre completo (nombre y apellidos)"
            etStudent.requestFocus()
            return null
        }
        return name
    }

    private fun scanQr() {
        if (studentNameOrError() == null) return
        pendingJoin?.let { joinLan(it); return }
        val options = GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .enableAutoZoom()
            .build()
        GmsBarcodeScanning.getClient(this, options).startScan()
            .addOnSuccessListener { barcode ->
                val info = LanClient.parse(barcode.rawValue.orEmpty())
                if (info == null) toast("Ese QR no es de un examen de Examen Seguro") else joinLan(info)
            }
            .addOnFailureListener {
                toast("No se pudo abrir el escáner. Escribe el código que muestra el docente.")
                manualCode()
            }
    }

    private fun manualCode() {
        if (studentNameOrError() == null) return
        val input = EditText(this).apply {
            hint = "192.168.1.10:8765 ABC123"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
        }
        val pad = (24 * resources.displayMetrics.density).toInt()
        MaterialAlertDialogBuilder(this)
            .setTitle("Código del examen")
            .setMessage("Escribe la dirección y el código que aparecen debajo del QR, separados por un espacio.")
            .setView(FrameLayout(this).apply { setPadding(pad, 0, pad, 0); addView(input) })
            .setPositiveButton("Entrar") { _, _ ->
                val info = LanClient.parse(input.text.toString())
                if (info == null) toast("Formato no válido. Ejemplo: 192.168.1.10:8765 ABC123") else joinLan(info)
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    @SuppressLint("HardwareIds")
    private fun joinLan(info: LanInfo) {
        val name = studentNameOrError()
        if (name == null) {
            pendingJoin = info
            toast("Escribe tu nombre completo y pulsa «Escanear QR» para entrar")
            return
        }
        if (joining) return
        joining = true
        pendingJoin = null
        config.studentName = name
        hideKeyboard()
        btnScan.isEnabled = false
        btnScan.text = "Conectando…"
        val deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID).orEmpty()
        Thread {
            val r = LanClient.join(info, name, deviceId)
            runOnUiThread {
                joining = false
                btnScan.isEnabled = true
                btnScan.text = "Escanear QR del docente"
                if (!r.ok) {
                    MaterialAlertDialogBuilder(this)
                        .setTitle("No se pudo entrar al examen")
                        .setMessage(r.message)
                        .setPositiveButton("Entendido", null)
                        .show()
                    return@runOnUiThread
                }
                startActivity(
                    Intent(this, ExamActivity::class.java)
                        .putExtra(ExamActivity.EXTRA_SERVER, info.server)
                        .putExtra(ExamActivity.EXTRA_TOKEN, r.token)
                        .putExtra(ExamActivity.EXTRA_URL, r.url)
                        .putExtra(ExamActivity.EXTRA_NAME, r.name)
                        .putExtra(ExamActivity.EXTRA_REQUIRE_LOCK, r.requireLock)
                )
            }
        }.start()
    }

    // ------------------------------------------------------------------ enlaces

    /** examenseguro://config?url=https://...&dominios=a.com,b.com&bloqueo=1
     *  examenseguro://unirse?s=IP:PUERTO&c=CODIGO */
    private fun handleDeepLink(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme != "examenseguro") return
        if (data.host == "unirse") {
            intent.data = null
            LanClient.parse(data.toString())?.let { joinLan(it) }
            return
        }
        if (data.host != "config") return
        intent.data = null
        if (!teacherEditable()) {
            pendingLink = data
            toast("Desbloquea la configuración con el PIN para importar el enlace")
            return
        }
        applyLink(data)
    }

    private fun applyLink(data: Uri) {
        data.getQueryParameter("url")?.let { etUrl.setText(it) }
        data.getQueryParameter("dominios")?.let { etDomains.setText(ExamConfig.parseHosts(it).joinToString(", ")) }
        data.getQueryParameter("bloqueo")?.let { swLock.isChecked = it != "0" }
        toast("Datos importados del enlace. Revisa y pulsa Guardar.")
    }

    private fun hideKeyboard() {
        currentFocus?.let {
            getSystemService(InputMethodManager::class.java)?.hideSoftInputFromWindow(it.windowToken, 0)
        }
    }
}
