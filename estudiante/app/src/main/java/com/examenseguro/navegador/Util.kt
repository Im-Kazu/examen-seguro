package com.examenseguro.navegador

import android.app.Activity
import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.Context
import android.os.Build
import android.provider.Settings
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.Toast
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import java.io.File

/** Receptor de administración: solo se usa si el docente/TI registra la app como propietaria del dispositivo. */
class AdminReceiver : DeviceAdminReceiver()

fun Context.toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()

/** Respeta barras del sistema, recortes de cámara y teclado (Android 15 es edge-to-edge). */
fun View.applySystemInsets() {
    ViewCompat.setOnApplyWindowInsetsListener(this) { v, insets ->
        val bars = insets.getInsets(
            WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
        )
        val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
        v.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, ime.bottom))
        WindowInsetsCompat.CONSUMED
    }
}

/** Diálogo para pedir el PIN del docente. */
object PinDialog {
    fun show(
        activity: Activity,
        config: ExamConfig,
        title: String,
        message: String,
        onDismiss: () -> Unit = {},
        onWrong: () -> Unit = {},
        onOk: () -> Unit,
    ) {
        val input = EditText(activity).apply {
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
            hint = "PIN del docente"
        }
        val pad = (24 * activity.resources.displayMetrics.density).toInt()
        val box = FrameLayout(activity).apply { setPadding(pad, pad / 2, pad, 0); addView(input) }
        MaterialAlertDialogBuilder(activity)
            .setTitle(title)
            .setMessage(message)
            .setView(box)
            .setPositiveButton("Aceptar") { _, _ ->
                when (val r = config.verifyPin(input.text.toString())) {
                    is ExamConfig.PinResult.Ok -> onOk()
                    is ExamConfig.PinResult.Wrong -> {
                        activity.toast("PIN incorrecto. Intentos restantes: ${r.remaining}")
                        onWrong()
                    }
                    is ExamConfig.PinResult.Locked -> {
                        activity.toast("Demasiados intentos. Espera ${r.seconds} s")
                        onWrong()
                    }
                }
            }
            .setNegativeButton("Cancelar", null)
            .setOnDismissListener { onDismiss() }
            .show()
    }
}

/** Comprobaciones del dispositivo que el docente debería conocer antes del examen. */
object DeviceChecks {

    fun isDeviceOwner(ctx: Context): Boolean =
        ctx.getSystemService(DevicePolicyManager::class.java)?.isDeviceOwnerApp(ctx.packageName) == true

    fun warnings(ctx: Context): List<String> {
        val cr = ctx.contentResolver
        val list = mutableListOf<String>()
        if (Settings.Global.getInt(cr, Settings.Global.ADB_ENABLED, 0) == 1)
            list += "Depuración USB activada"
        if (Settings.Global.getInt(cr, Settings.Global.DEVELOPMENT_SETTINGS_ENABLED, 0) == 1)
            list += "Opciones de desarrollador activadas"
        val acc = Settings.Secure.getString(cr, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES)
        if (!acc.isNullOrBlank())
            list += "Servicios de accesibilidad activos (pueden leer la pantalla): ${shortNames(acc)}"
        if (looksRooted()) list += "Posible dispositivo con root"
        if (looksLikeEmulator()) list += "Parece un emulador"
        return list
    }

    private fun shortNames(acc: String) =
        acc.split(':').mapNotNull { it.substringBefore('/').takeIf(String::isNotBlank) }
            .joinToString(", ")

    private fun looksRooted(): Boolean {
        if (Build.TAGS?.contains("test-keys") == true) return true
        val paths = listOf(
            "/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su",
            "/data/local/xbin/su", "/data/local/bin/su", "/system/app/Superuser.apk",
            "/data/adb/magisk", "/data/adb/ksu"
        )
        return paths.any { runCatching { File(it).exists() }.getOrDefault(false) }
    }

    private fun looksLikeEmulator(): Boolean =
        Build.FINGERPRINT.startsWith("generic") || Build.MODEL.contains("Emulator") ||
            Build.MODEL.contains("Android SDK built for") || Build.HARDWARE.contains("ranchu") ||
            Build.HARDWARE.contains("goldfish")
}
