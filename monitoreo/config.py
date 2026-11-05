"""Configuración de la aplicación a partir de variables de entorno.

Las credenciales por defecto son admin / admin123 y se pueden cambiar con
ADMIN_USER y ADMIN_PASSWORD. La clave de sesión se lee de SECRET_KEY; si no
existe, se genera una sola vez y se guarda junto a la base de datos, para que
todos los workers de gunicorn compartan el mismo valor.
"""

import logging
import os
import secrets

log = logging.getLogger(__name__)

SITIOS_POR_DEFECTO = "https://www.google.com,https://www.github.com"
USUARIO_POR_DEFECTO = "admin"
CLAVE_POR_DEFECTO = "admin123"


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
    log.info("Se generó %s y se guardó en %s", descripcion, ruta)
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
        "ADMIN_USER": os.environ.get("ADMIN_USER") or USUARIO_POR_DEFECTO,
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
        cfg["ADMIN_PASSWORD"] = os.environ.get("ADMIN_PASSWORD") or CLAVE_POR_DEFECTO

    return cfg
