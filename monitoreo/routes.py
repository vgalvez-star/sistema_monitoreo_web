"""Páginas y API JSON."""

import math
import re
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from . import db
from .auth import login_requerido, token_csrf

bp = Blueprint("web", __name__)

ESTADOS = ("OK", "LENTO", "ERROR")


def _db():
    return current_app.config["DB_PATH"]


def validar_url(texto):
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("Escribe una URL")
    if not re.match(r"^https?://", texto, re.IGNORECASE):
        texto = "https://" + texto
    partes = urlparse(texto)
    if (
        partes.scheme.lower() not in {"http", "https"}
        or not partes.hostname
        or "." not in partes.hostname and partes.hostname != "localhost"
        or len(texto) > 2048
        or any(c.isspace() for c in texto)
    ):
        raise ValueError("La URL no es válida")
    return texto


def _entero_arg(nombre, defecto, minimo, maximo):
    try:
        valor = int(request.args.get(nombre, defecto))
    except (TypeError, ValueError):
        valor = defecto
    return max(minimo, min(valor, maximo))


# ------------------------------------------------------------------ páginas

@bp.route("/")
@login_requerido
def dashboard():
    return render_template(
        "dashboard.html",
        csrf=token_csrf(),
        intervalo=current_app.config["INTERVALO_SEGUNDOS"],
        umbral_lento=current_app.config["UMBRAL_LENTO_MS"],
    )


@bp.route("/historial")
@login_requerido
def ver_historial():
    por_pagina = 25
    pagina = _entero_arg("pagina", 1, 1, 100000)
    sitio_id = request.args.get("sitio", type=int)
    estado = request.args.get("estado")
    estado = estado if estado in ESTADOS else None
    filas, total = db.historial(
        _db(), sitio_id, estado, limite=por_pagina, offset=(pagina - 1) * por_pagina
    )
    return render_template(
        "historial.html",
        csrf=token_csrf(),
        filas=filas,
        total=total,
        pagina=pagina,
        paginas=max(1, math.ceil(total / por_pagina)),
        sitios=db.listar_sitios(_db()),
        sitio_id=sitio_id,
        estado=estado,
    )


@bp.route("/health")
def health():
    """Comprobación pública para el balanceador de Render."""
    return jsonify(ok=True)


# ---------------------------------------------------------------------- API

@bp.route("/api/status")
@login_requerido
def api_status():
    sitios = db.resumen(_db())
    con_datos = [s for s in sitios if s["estado"] != "SIN_DATOS"]
    latencias = [s["tiempo_ms"] for s in con_datos if s["tiempo_ms"] is not None and s["estado"] != "ERROR"]
    uptimes = [s["uptime_24h"] for s in sitios if s["uptime_24h"] is not None]
    return jsonify(
        sitios=sitios,
        resumen={
            "total": len(sitios),
            "operativos": sum(s["estado"] == "OK" for s in sitios),
            "lentos": sum(s["estado"] == "LENTO" for s in sitios),
            "caidos": sum(s["estado"] == "ERROR" for s in sitios),
            "sin_datos": sum(s["estado"] == "SIN_DATOS" for s in sitios),
            "latencia_promedio_ms": round(sum(latencias) / len(latencias), 1) if latencias else None,
            "uptime_24h": round(sum(uptimes) / len(uptimes), 2) if uptimes else None,
        },
        intervalo=current_app.config["INTERVALO_SEGUNDOS"],
        servidor_utc=db.iso(db.ahora_utc()),
    )


@bp.route("/api/serie/<int:sitio_id>")
@login_requerido
def api_serie(sitio_id):
    limite = _entero_arg("limite", 120, 10, 1000)
    return jsonify(sitio_id=sitio_id, puntos=db.serie(_db(), sitio_id, limite))


@bp.route("/api/historial")
@login_requerido
def api_historial():
    limite = _entero_arg("limite", 20, 1, 500)
    offset = _entero_arg("offset", 0, 0, 10**9)
    estado = request.args.get("estado")
    filas, total = db.historial(
        _db(),
        request.args.get("sitio", type=int),
        estado if estado in ESTADOS else None,
        limite,
        offset,
    )
    return jsonify(total=total, registros=filas)


@bp.route("/api/sitios", methods=["POST"])
@login_requerido
def api_agregar_sitio():
    datos = request.get_json(silent=True) or {}
    try:
        url = validar_url(datos.get("url"))
        sitio = db.agregar_sitio(_db(), url, datos.get("nombre"))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(sitio), 201


@bp.route("/api/sitios/<int:sitio_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_sitio(sitio_id):
    if not db.eliminar_sitio(_db(), sitio_id):
        abort(404)
    return "", 204
