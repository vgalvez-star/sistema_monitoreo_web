import re
from unittest import mock

import pytest
import requests

from monitoreo import create_app, db
from monitoreo.checker import Resultado, chequear
from monitoreo.routes import validar_url
from monitoreo.scheduler import Monitor


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "DB_PATH": str(tmp_path / "test.db"),
            "SECRET_KEY": "test",
            "ADMIN_PASSWORD": "clave-segura",
            "MONITOR_ACTIVO": False,
            "SITIOS_INICIALES": ["https://ejemplo.cl"],
            "TESTING": True,
        }
    )


@pytest.fixture
def cliente(app):
    return app.test_client()


def csrf_de(html):
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def iniciar_sesion(cliente, clave="clave-segura"):
    pagina = cliente.get("/login").get_data(as_text=True)
    token = csrf_de(pagina)
    return cliente.post(
        "/login", data={"username": "admin", "password": clave, "csrf_token": token}
    )


@pytest.fixture
def sesion(cliente):
    assert iniciar_sesion(cliente).status_code == 302
    return csrf_de(cliente.get("/").get_data(as_text=True))


# ------------------------------------------------------------ autenticación

def test_rutas_protegidas_requieren_login(cliente):
    assert cliente.get("/").status_code == 302
    assert cliente.get("/historial").status_code == 302
    assert cliente.get("/api/status").status_code == 401


def test_health_es_publico(cliente):
    assert cliente.get("/health").get_json() == {"ok": True}


def test_login_incorrecto(cliente):
    r = iniciar_sesion(cliente, clave="1234")
    assert r.status_code == 401
    assert "incorrectos" in r.get_data(as_text=True)


def test_login_sin_csrf_rechazado(cliente):
    r = cliente.post("/login", data={"username": "admin", "password": "clave-segura"})
    assert r.status_code == 400


def test_login_no_redirige_fuera_del_sitio(cliente):
    token = csrf_de(cliente.get("/login").get_data(as_text=True))
    r = cliente.post(
        "/login?siguiente=//malicioso.com",
        data={"username": "admin", "password": "clave-segura", "csrf_token": token},
    )
    assert r.headers["Location"] == "/"


def test_bloqueo_tras_varios_fallos(cliente):
    for _ in range(5):
        iniciar_sesion(cliente, clave="mala")
    assert iniciar_sesion(cliente).status_code == 429


# --------------------------------------------------------------------- API

def test_status_inicial(cliente, sesion):
    datos = cliente.get("/api/status").get_json()
    assert datos["resumen"]["total"] == 1
    assert datos["sitios"][0]["estado"] == "SIN_DATOS"


def test_agregar_y_eliminar_sitio(cliente, sesion):
    r = cliente.post("/api/sitios", json={"url": "github.com"}, headers={"X-CSRF-Token": sesion})
    assert r.status_code == 201
    sitio = r.get_json()
    assert sitio["url"] == "https://github.com" and sitio["nombre"] == "github.com"

    duplicado = cliente.post("/api/sitios", json={"url": "https://github.com"}, headers={"X-CSRF-Token": sesion})
    assert duplicado.status_code == 400

    assert cliente.delete(f"/api/sitios/{sitio['id']}", headers={"X-CSRF-Token": sesion}).status_code == 204
    assert cliente.delete(f"/api/sitios/{sitio['id']}", headers={"X-CSRF-Token": sesion}).status_code == 404


def test_api_mutaciones_requieren_csrf(cliente, sesion):
    assert cliente.post("/api/sitios", json={"url": "github.com"}).status_code == 400


def test_resumen_y_uptime(app, cliente, sesion):
    ruta = app.config["DB_PATH"]
    sitio_id = db.listar_sitios(ruta)[0]["id"]
    for r in [Resultado("OK", 200, 120.0), Resultado("OK", 200, 80.0), Resultado("ERROR", error="x"), Resultado("LENTO", 200, 2000.0)]:
        db.registrar_chequeo(ruta, sitio_id, r)
    s = cliente.get("/api/status").get_json()["sitios"][0]
    assert s["estado"] == "LENTO"
    assert s["uptime_24h"] == 75.0
    assert s["promedio_ms_24h"] == pytest.approx((120 + 80 + 2000) / 3, abs=0.1)
    assert len(s["serie"]) == 4
    assert cliente.get(f"/api/serie/{sitio_id}").get_json()["puntos"][-1]["estado"] == "LENTO"

    hist = cliente.get("/api/historial?estado=ERROR").get_json()
    assert hist["total"] == 1 and hist["registros"][0]["error"] == "x"


def test_paginas_renderizan(cliente, sesion):
    assert "data-cielo" in cliente.get("/").get_data(as_text=True)
    assert "Historial de chequeos" in cliente.get("/historial?estado=OK&pagina=abc").get_data(as_text=True)


# ------------------------------------------------------------------- lógica

@pytest.mark.parametrize("entrada", ["", "ftp://x.com", "https://", "no es url", "https://localhost x"])
def test_validar_url_rechaza(entrada):
    with pytest.raises(ValueError):
        validar_url(entrada)


def test_validar_url_agrega_esquema():
    assert validar_url("  www.duoc.cl ") == "https://www.duoc.cl"


def _respuesta(codigo):
    r = mock.Mock(status_code=codigo, reason="Not Found")
    return r


def test_chequear_clasifica_resultados():
    sesion = mock.Mock()
    sesion.get.return_value = _respuesta(200)
    assert chequear("https://a.cl", session=sesion).estado == "OK"

    sesion.get.return_value = _respuesta(404)
    r = chequear("https://a.cl", session=sesion)
    assert r.estado == "ERROR" and r.codigo_http == 404

    sesion.get.side_effect = requests.exceptions.ConnectTimeout()
    assert "timeout" in chequear("https://a.cl", session=sesion).error

    sesion.get.side_effect = requests.exceptions.SSLError()
    assert "SSL" in chequear("https://a.cl", session=sesion).error

    sesion.get.side_effect = requests.exceptions.ConnectionError()
    assert "conectar" in chequear("https://a.cl", session=sesion).error


def test_chequear_marca_lento():
    sesion = mock.Mock()
    sesion.get.return_value = _respuesta(200)
    assert chequear("https://a.cl", umbral_lento_ms=-1, session=sesion).estado == "LENTO"


def test_ciclo_de_monitor_registra(app):
    ruta = app.config["DB_PATH"]
    monitor = Monitor(ruta)
    with mock.patch("monitoreo.scheduler.chequear", return_value=Resultado("OK", 200, 50.0)):
        assert monitor.ejecutar_ciclo() == 1
    assert db.historial(ruta)[1] == 1


def test_un_solo_monitor_por_base_de_datos(app):
    ruta = app.config["DB_PATH"]
    a, b = Monitor(ruta, intervalo=3600), Monitor(ruta, intervalo=3600)
    with mock.patch("monitoreo.scheduler.chequear", return_value=Resultado("OK", 200, 50.0)):
        try:
            assert a.iniciar() is True
            assert b.iniciar() is False
        finally:
            a.detener()
            b.detener()
