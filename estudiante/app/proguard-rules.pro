# ==========================================================================
#  Examen Seguro — reglas de ofuscación / endurecimiento (R8 en modo full)
# ==========================================================================
# La app no expone interfaces @JavascriptInterface, así que no hay que
# conservar métodos para JS. Todo lo que no se use se elimina y se renombra.

# --- Ofuscación agresiva -------------------------------------------------
-repackageclasses ''            # junta todo en un solo paquete sin nombre
-allowaccessmodification         # permite cambiar modificadores para optimizar
-optimizationpasses 5
-overloadaggressively

# --- Borra el log en release (no deja rastros ni mensajes legibles) -------
-assumenosideeffects class android.util.Log {
    public static *** v(...);
    public static *** d(...);
    public static *** i(...);
    public static *** w(...);
    public static *** e(...);
}

# --- Quita los números de línea y nombres de archivo del stacktrace -------
# (si algún día quieres depurar un crash, comenta estas dos líneas)
-renamesourcefileattribute ''
# Conservamos solo lo mínimo para que el sistema arranque las pantallas.

# Las Activities, el BroadcastReceiver (AdminReceiver) y demás componentes
# declarados en el Manifest los conserva AAPT automáticamente; el resto del
# código Kotlin se ofusca.

# --- Dependencias que usan reflexión interna -----------------------------
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
