"""Bucle de monitoreo en segundo plano.

Un candado de archivo asegura que solo UN proceso ejecute el monitoreo, aunque
gunicorn levante varios workers o Flask use el recargador en modo debug.
"""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from . import db
from .checker import chequear

log = logging.getLogger(__name__)


def _adquirir_candado(ruta):
    archivo = open(ruta, "a+")
    try:
        try:
            import fcntl

            fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:  # Windows
            import msvcrt

            archivo.seek(0)
            msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        archivo.close()
        return None
    return archivo


class Monitor:
    def __init__(self, db_path, intervalo=15, timeout=5, umbral_lento_ms=1500, retencion_dias=7):
        self.db_path = db_path
        self.intervalo = intervalo
        self.timeout = timeout
        self.umbral_lento_ms = umbral_lento_ms
        self.retencion_dias = retencion_dias
        self._detener = threading.Event()
        self._hilo = None
        self._candado = None
        self._ultima_purga = 0.0
        self._local = threading.local()

    def _sesion(self):
        # Una sesión HTTP por hilo reutiliza conexiones entre ciclos.
        if not hasattr(self._local, "sesion"):
            self._local.sesion = requests.Session()
        return self._local.sesion

    def _chequear_sitio(self, sitio):
        return sitio, chequear(sitio["url"], self.timeout, self.umbral_lento_ms, self._sesion())

    def ejecutar_ciclo(self):
        sitios = db.listar_sitios(self.db_path)
        if not sitios:
            return 0
        with ThreadPoolExecutor(max_workers=min(8, len(sitios))) as pool:
            resultados = list(pool.map(self._chequear_sitio, sitios))
        for sitio, resultado in resultados:
            db.registrar_chequeo(self.db_path, sitio["id"], resultado)
            if resultado.estado == "ERROR":
                log.info("%s -> ERROR: %s", sitio["url"], resultado.error)
        return len(resultados)

    def _purgar_si_corresponde(self):
        if time.monotonic() - self._ultima_purga >= 3600:
            borrados = db.purgar_antiguos(self.db_path, self.retencion_dias)
            self._ultima_purga = time.monotonic()
            if borrados:
                log.info("Se purgaron %d chequeos con más de %d días", borrados, self.retencion_dias)

    def _bucle(self):
        log.info("Monitoreo iniciado (cada %d s)", self.intervalo)
        while not self._detener.is_set():
            inicio = time.monotonic()
            try:
                self.ejecutar_ciclo()
                self._purgar_si_corresponde()
            except Exception:  # el hilo nunca debe morir por un ciclo fallido
                log.exception("Falló un ciclo de monitoreo")
            espera = max(1.0, self.intervalo - (time.monotonic() - inicio))
            self._detener.wait(espera)

    def iniciar(self):
        self._candado = _adquirir_candado(os.path.abspath(self.db_path) + ".lock")
        if self._candado is None:
            log.info("Otro proceso ya ejecuta el monitoreo; este worker solo sirve la web")
            return False
        self._hilo = threading.Thread(target=self._bucle, name="monitor", daemon=True)
        self._hilo.start()
        return True

    def detener(self):
        self._detener.set()
        if self._hilo:
            self._hilo.join(timeout=self.timeout + 2)
        if self._candado:
            self._candado.close()
