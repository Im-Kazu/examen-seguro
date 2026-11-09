package com.examenseguro.navegador

import android.net.Uri
import android.os.Build
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/** Datos que vienen en el QR del panel del docente. */
data class LanInfo(val server: String, val code: String)

/** Resultado de unirse al examen. */
data class JoinResult(
    val ok: Boolean,
    val message: String,
    val token: String = "",
    val url: String = "",
    val title: String = "",
    val name: String = "",
    val requireLock: Boolean = true,
)

/** Cliente HTTP mínimo para hablar con el panel del docente en la red local. */
object LanClient {

    private val queue = Executors.newSingleThreadExecutor()
    val userAgent = "${ExamActivity.USER_AGENT_SUFFIX} (Android ${Build.VERSION.RELEASE}; ${Build.MODEL})"

    /** Acepta "examenseguro://unirse?s=IP:PUERTO&c=CODIGO" o, a mano, "IP:PUERTO CODIGO". */
    fun parse(text: String): LanInfo? {
        val t = text.trim()
        if (t.startsWith("examenseguro://", ignoreCase = true)) {
            val uri = Uri.parse(t)
            if (uri.host != "unirse") return null
            val s = uri.getQueryParameter("s") ?: return null
            val c = uri.getQueryParameter("c") ?: return null
            return LanInfo(normalizeServer(s), c.trim().uppercase())
        }
        val parts = t.split(Regex("\\s+"))
        if (parts.size == 2 && parts[0].contains('.')) return LanInfo(normalizeServer(parts[0]), parts[1].uppercase())
        return null
    }

    private fun normalizeServer(s: String): String {
        val withScheme = if (s.startsWith("http://") || s.startsWith("https://")) s else "http://$s"
        return withScheme.trimEnd('/')
    }

    /** Bloqueante: llamar fuera del hilo principal. */
    fun join(info: LanInfo, name: String, deviceId: String): JoinResult = try {
        val body = JSONObject()
            .put("nombre", name).put("codigo", info.code)
            .put("dispositivo", deviceId).put("modelo", "${Build.MANUFACTURER} ${Build.MODEL}")
        val (code, json) = post(info.server, "/api/unirse", body)
        if (code == 200 && json != null) {
            JoinResult(
                ok = true, message = "",
                token = json.getString("token"),
                url = info.server + json.getString("url"),
                title = json.optString("titulo"),
                name = json.optString("nombre", name),
                requireLock = json.optBoolean("bloqueo", true),
            )
        } else {
            JoinResult(false, json?.optString("error") ?: "El servidor respondió con error $code")
        }
    } catch (e: IOException) {
        JoinResult(false, "No se pudo conectar con la computadora del docente (${info.server}).\n" +
            "Revisa que estés en la misma red Wi-Fi.")
    }

    /** Envía telemetría en segundo plano (con reintentos). */
    fun telemetry(server: String, token: String, type: String, detail: String) {
        queue.execute {
            val body = JSONObject().put("t", token).put("tipo", type).put("detalle", detail)
            retry(3) { post(server, "/api/telemetria", body) }
        }
    }

    /** Avisa al servidor que el examen se terminó por salir de la app. */
    fun terminate(server: String, token: String, reason: String, done: (Boolean) -> Unit = {}) {
        queue.execute {
            val body = JSONObject().put("t", token).put("motivo", reason)
            done(retry(6) { post(server, "/api/terminar", body) })
        }
    }

    private fun retry(times: Int, call: () -> Pair<Int, JSONObject?>): Boolean {
        repeat(times) { attempt ->
            try {
                val (code, _) = call()
                if (code in 200..499) return code < 300
            } catch (_: IOException) {
            }
            Thread.sleep(1000L * (attempt + 1))
        }
        return false
    }

    private fun post(server: String, path: String, body: JSONObject): Pair<Int, JSONObject?> {
        val conn = URL(server + path).openConnection() as HttpURLConnection
        try {
            conn.requestMethod = "POST"
            conn.connectTimeout = 6000
            conn.readTimeout = 8000
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            conn.setRequestProperty("User-Agent", userAgent)
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code < 400) conn.inputStream else conn.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            return code to runCatching { JSONObject(text) }.getOrNull()
        } finally {
            conn.disconnect()
        }
    }
}
