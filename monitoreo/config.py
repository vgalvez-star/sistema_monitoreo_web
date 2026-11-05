"""Configuración de la aplicación a partir de variables de entorno.

Nada sensible queda escrito en el código: la clave de sesión y la contraseña
del administrador se leen del entorno. Si no existen, se generan una sola vez
y se guardan junto a la base de datos, para que todos los workers de gunicorn
compartan los mismos valores.
"""

import logging
import os
import secrets

log = logging.getLogger(__name__)

SITIOS_POR_DEFECTO = "https://www.google.com,https://www.github.com"


def _entero(nombre, defecto, minimo):
    valor = os.environ.get(nombre)
    if valor is None or valor.strip() == "":
        return defecto
    try:
        numero = int(valor)
    except ValueError:
        log.warning("%s=%r no es un entero; se usa %s", nombre, valor, defecto)
        return defecto
    return max(numero, minimo)


def _booleano(nombre, defecto=False):
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def _secreto_persistente(ruta, generar, descripcion):
    """Lee un secreto desde `ruta`; si no existe, lo crea de forma atómica.

    O_EXCL garantiza que, si varios procesos arrancan a la vez, solo uno lo
    escriba y el resto lea el mismo valor.
    """
    try:
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        with open(ruta, encoding="utf-8") as f:
            return f.read().strip(), False
    valor = generar()
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(valor)
    log.warning("Se generó %s y se guardó en %s", descripcion, ruta)
    return valor, True


def cargar_config(overrides=None):
    overrides = overrides or {}
    db_path = overrides.get("DB_PATH") or os.environ.get("DB_PATH", "monitor.db")
    carpeta = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(carpeta, exist_ok=True)

    cfg = {
        "DB_PATH": db_path,
        "INTERVALO_SEGUNDOS": _entero("CHECK_INTERVAL", 15, minimo=5),
        "TIMEOUT_SEGUNDOS": _entero("REQUEST_TIMEOUT", 5, minimo=1),
        "UMBRAL_LENTO_MS": _entero("SLOW_THRESHOLD_MS", 1500, minimo=100),
        "RETENCION_DIAS": _entero("RETENTION_DAYS", 7, minimo=1),
        "SITIOS_INICIALES": [
            s.strip()
            for s in os.environ.get("MONITOR_SITES", SITIOS_POR_DEFECTO).split(",")
            if s.strip()
        ],
        "MONITOR_ACTIVO": _booleano("MONITOR_ENABLED", True),
        "ADMIN_USER": os.environ.get("ADMIN_USER", "admin"),
        "TRUST_PROXY": _booleano("TRUST_PROXY", False),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": _booleano("SESSION_COOKIE_SECURE", False),
        "PERMANENT_SESSION_LIFETIME": 60 * 60 * 12,
    }
    cfg.update(overrides)

    if "SECRET_KEY" not in cfg:
        cfg["SECRET_KEY"] = os.environ.get("SECRET_KEY") or _secreto_persistente(
            os.path.join(carpeta, ".secret_key"),
            lambda: secrets.token_hex(32),
            "una SECRET_KEY",
        )[0]

    if "ADMIN_PASSWORD" not in cfg:
        clave = os.environ.get("ADMIN_PASSWORD")
        if not clave:
            clave, nueva = _secreto_persistente(
                os.path.join(carpeta, ".admin_password"),
                lambda: secrets.token_urlsafe(12),
                "una contraseña de administrador",
            )
            if nueva:
                log.warning(
                    "ADMIN_PASSWORD no está definida. Contraseña generada para '%s': %s",
                    cfg["ADMIN_USER"],
                    clave,
                )
        cfg["ADMIN_PASSWORD"] = clave

    return cfg
