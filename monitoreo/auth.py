"""Inicio de sesión, protección de rutas y token CSRF."""

import hmac
import secrets
import threading
import time
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

bp = Blueprint("auth", __name__)

MAX_INTENTOS = 5
VENTANA_SEGUNDOS = 600


def _registro_intentos():
    """Fallos de login por IP, guardados por aplicación (en memoria del worker)."""
    return current_app.extensions.setdefault(
        "intentos_login", {"por_ip": {}, "lock": threading.Lock()}
    )


def _bloqueado(ip):
    reg = _registro_intentos()
    ahora = time.time()
    with reg["lock"]:
        recientes = [t for t in reg["por_ip"].get(ip, []) if ahora - t < VENTANA_SEGUNDOS]
        if recientes:
            reg["por_ip"][ip] = recientes
        else:
            reg["por_ip"].pop(ip, None)
        return len(recientes) >= MAX_INTENTOS


def _registrar_fallo(ip):
    reg = _registro_intentos()
    with reg["lock"]:
        reg["por_ip"].setdefault(ip, []).append(time.time())


def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_valido():
    enviado = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    esperado = session.get("csrf", "")
    return bool(esperado) and hmac.compare_digest(enviado, esperado)


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not session.get("usuario"):
            if request.path.startswith("/api/"):
                return jsonify(error="No autenticado"), 401
            return redirect(url_for("auth.login", siguiente=request.full_path))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not csrf_valido():
            return jsonify(error="Token CSRF inválido"), 400
        return vista(*args, **kwargs)

    return envoltura


def _destino_seguro(destino):
    # Solo rutas internas: evita redirecciones abiertas a otros dominios.
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino.rstrip("?") or "/"
    return url_for("web.dashboard")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("usuario"):
        return redirect(url_for("web.dashboard"))

    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _bloqueado(ip):
            flash("Demasiados intentos fallidos. Espera unos minutos.", "error")
            return render_template("login.html", csrf=token_csrf()), 429
        if not csrf_valido():
            flash("La sesión del formulario expiró. Inténtalo de nuevo.", "error")
            return render_template("login.html", csrf=token_csrf()), 400

        usuario = request.form.get("username", "").strip()
        clave = request.form.get("password", "")
        usuario_ok = hmac.compare_digest(usuario, current_app.config["ADMIN_USER"])
        clave_ok = check_password_hash(current_app.config["ADMIN_PASSWORD_HASH"], clave)
        if usuario_ok and clave_ok:
            session.clear()
            session.permanent = True
            session["usuario"] = usuario
            token_csrf()
            return redirect(_destino_seguro(request.args.get("siguiente")))

        _registrar_fallo(ip)
        time.sleep(0.4)
        flash("Usuario o contraseña incorrectos.", "error")
        return render_template("login.html", csrf=token_csrf(), usuario=usuario), 401

    return render_template("login.html", csrf=token_csrf())


@bp.route("/logout", methods=["POST"])
def logout():
    if csrf_valido():
        session.clear()
    return redirect(url_for("auth.login"))
