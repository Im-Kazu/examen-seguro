package com.examenseguro.navegador

import android.content.Context
import android.net.Uri
import android.util.Base64
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/** Configuración persistente del examen (la define el docente). */
class ExamConfig(context: Context) {

    sealed class PinResult {
        object Ok : PinResult()
        data class Wrong(val remaining: Int) : PinResult()
        data class Locked(val seconds: Int) : PinResult()
    }

    private val prefs = context.getSharedPreferences("exam_config", Context.MODE_PRIVATE)

    var examUrl: String
        get() = prefs.getString(K_URL, "") ?: ""
        set(v) = prefs.edit().putString(K_URL, v).apply()

    /** Dominios adicionales (el dominio de la URL del examen siempre se permite). */
    var extraHosts: List<String>
        get() = (prefs.getString(K_HOSTS, "") ?: "").split('\n').filter { it.isNotBlank() }
        set(v) = prefs.edit().putString(K_HOSTS, v.joinToString("\n")).apply()

    var requireLock: Boolean
        get() = prefs.getBoolean(K_REQUIRE_LOCK, true)
        set(v) = prefs.edit().putBoolean(K_REQUIRE_LOCK, v).apply()

    var studentName: String
        get() = prefs.getString(K_STUDENT, "") ?: ""
        set(v) = prefs.edit().putString(K_STUDENT, v).apply()

    fun allowedHosts(): List<String> {
        val main = Uri.parse(examUrl).host?.lowercase()
        return (listOfNotNull(main) + extraHosts).distinct()
    }

    /** Solo HTTPS y solo hosts de la lista blanca (incluye subdominios). */
    fun isAllowed(uri: Uri): Boolean {
        if (uri.toString() == "about:blank") return true
        if (uri.scheme?.lowercase() != "https") return false
        val host = uri.host?.lowercase() ?: return false
        return allowedHosts().any { host == it || host.endsWith(".$it") }
    }

    // ---------- PIN del docente (PBKDF2 con sal) ----------

    fun hasPin(): Boolean = !prefs.getString(K_PIN_HASH, null).isNullOrEmpty()

    fun setPin(pin: String) {
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        prefs.edit()
            .putString(K_PIN_SALT, Base64.encodeToString(salt, Base64.NO_WRAP))
            .putString(K_PIN_HASH, hash(pin, salt))
            .putInt(K_FAILS, 0)
            .putLong(K_LOCK_UNTIL, 0)
            .apply()
    }

    fun verifyPin(pin: String): PinResult {
        val now = System.currentTimeMillis()
        val until = prefs.getLong(K_LOCK_UNTIL, 0)
        if (now < until) return PinResult.Locked(((until - now) / 1000).toInt() + 1)

        val salt = Base64.decode(prefs.getString(K_PIN_SALT, "") ?: "", Base64.NO_WRAP)
        val stored = prefs.getString(K_PIN_HASH, "") ?: ""
        val ok = stored.isNotEmpty() &&
            MessageDigest.isEqual(stored.toByteArray(), hash(pin, salt).toByteArray())
        if (ok) {
            prefs.edit().putInt(K_FAILS, 0).apply()
            return PinResult.Ok
        }
        val fails = prefs.getInt(K_FAILS, 0) + 1
        if (fails >= MAX_FAILS) {
            prefs.edit().putInt(K_FAILS, 0).putLong(K_LOCK_UNTIL, now + LOCK_MS).apply()
            return PinResult.Locked((LOCK_MS / 1000).toInt())
        }
        prefs.edit().putInt(K_FAILS, fails).apply()
        return PinResult.Wrong(MAX_FAILS - fails)
    }

    private fun hash(pin: String, salt: ByteArray): String {
        val spec = PBEKeySpec(pin.toCharArray(), salt, 20_000, 256)
        val key = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded
        return Base64.encodeToString(key, Base64.NO_WRAP)
    }

    // ---------- Registro de incidentes del último examen ----------

    fun incidents(): List<String> =
        (prefs.getString(K_INCIDENTS, "") ?: "").split('\n').filter { it.isNotBlank() }

    fun clearIncidents() = prefs.edit().putString(K_INCIDENTS, "").apply()

    fun appendIncident(line: String) {
        val all = incidents() + line.replace('\n', ' ')
        prefs.edit().putString(K_INCIDENTS, all.joinToString("\n")).commit()
    }

    var lastReportHeader: String
        get() = prefs.getString(K_REPORT_HEADER, "") ?: ""
        set(v) = prefs.edit().putString(K_REPORT_HEADER, v).apply()

    companion object {
        private const val K_URL = "url"
        private const val K_HOSTS = "hosts"
        private const val K_REQUIRE_LOCK = "require_lock"
        private const val K_STUDENT = "student"
        private const val K_PIN_HASH = "pin_hash"
        private const val K_PIN_SALT = "pin_salt"
        private const val K_FAILS = "pin_fails"
        private const val K_LOCK_UNTIL = "pin_lock_until"
        private const val K_INCIDENTS = "incidents"
        private const val K_REPORT_HEADER = "report_header"
        private const val MAX_FAILS = 5
        private const val LOCK_MS = 60_000L

        /** Convierte "https://a.com/x, *.b.org; c.net" en [a.com, b.org, c.net]. */
        fun parseHosts(text: String): List<String> =
            text.split(Regex("[,;\\s]+"))
                .map { it.trim().lowercase() }
                .map { it.removePrefix("https://").removePrefix("http://").removePrefix("*.") }
                .map { it.substringBefore('/').substringBefore(':') }
                .filter { it.contains('.') }
                .distinct()
    }
}
