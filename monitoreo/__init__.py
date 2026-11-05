"""Sistema de Monitoreo Web — fábrica de la aplicación Flask."""

import atexit
import logging
import threading

from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from . import db
from .config import cargar_config
from .scheduler import Monitor

__version__ = "2.0.0"


def create_app(overrides=None):
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    app = Flask(__name__)
    app.config.update(cargar_config(overrides))
    app.config["ADMIN_PASSWORD_HASH"] = generate_password_hash(app.config.pop("ADMIN_PASSWORD"))

    if app.config["TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_db(app.config["DB_PATH"], app.config["SITIOS_INICIALES"])
    app.extensions["intentos_login"] = {"por_ip": {}, "lock": threading.Lock()}

    from .auth import bp as auth_bp
    from .routes import bp as web_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(web_bp)

    @app.context_processor
    def _globales():
        return {"version": __version__}

    @app.after_request
    def _cabeceras_seguridad(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.errorhandler(404)
    def _no_encontrado(_):
        if request.path.startswith("/api/"):
            return jsonify(error="No encontrado"), 404
        return "Página no encontrada", 404

    if app.config["MONITOR_ACTIVO"]:
        monitor = Monitor(
            app.config["DB_PATH"],
            app.config["INTERVALO_SEGUNDOS"],
            app.config["TIMEOUT_SEGUNDOS"],
            app.config["UMBRAL_LENTO_MS"],
            app.config["RETENCION_DIAS"],
        )
        if monitor.iniciar():
            atexit.register(monitor.detener)
        app.extensions["monitor"] = monitor

    return app
