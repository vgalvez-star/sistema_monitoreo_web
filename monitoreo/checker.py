"""Chequeo HTTP de un sitio, con errores clasificados (nada de `except:` ciego)."""

import time
from dataclasses import dataclass
from typing import Optional

import requests

USER_AGENT = "SistemaMonitoreoWeb/2.0 (+https://github.com/vgalvez-star/sistema_monitoreo_web)"


@dataclass
class Resultado:
    estado: str  # OK | LENTO | ERROR
    codigo_http: Optional[int] = None
    tiempo_ms: Optional[float] = None
    error: Optional[str] = None


def chequear(url, timeout=5, umbral_lento_ms=1500, session=None):
    cliente = session or requests
    inicio = time.perf_counter()
    try:
        # stream=True: medimos hasta recibir las cabeceras, sin descargar el cuerpo.
        respuesta = cliente.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            stream=True,
            headers={"User-Agent": USER_AGENT},
        )
        tiempo_ms = round((time.perf_counter() - inicio) * 1000, 1)
        respuesta.close()
    except requests.exceptions.SSLError:
        return Resultado("ERROR", error="Certificado SSL inválido o no confiable")
    except requests.exceptions.Timeout:
        return Resultado("ERROR", error=f"Sin respuesta en {timeout} s (timeout)")
    except requests.exceptions.TooManyRedirects:
        return Resultado("ERROR", error="Demasiadas redirecciones")
    except requests.exceptions.ConnectionError:
        return Resultado("ERROR", error="No se pudo conectar (DNS o servidor caído)")
    except requests.exceptions.RequestException as exc:
        return Resultado("ERROR", error=f"Error de solicitud: {type(exc).__name__}")

    codigo = respuesta.status_code
    if codigo >= 400:
        return Resultado("ERROR", codigo, tiempo_ms, f"HTTP {codigo} {respuesta.reason or ''}".strip())
    if tiempo_ms > umbral_lento_ms:
        return Resultado("LENTO", codigo, tiempo_ms)
    return Resultado("OK", codigo, tiempo_ms)
