"""Acceso a datos (SQLite).

Todo el estado vive en la base de datos y no en diccionarios en memoria, así
cualquier worker de gunicorn ve exactamente lo mismo.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

ESQUEMA = """
CREATE TABLE IF NOT EXISTS sitios (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    url       TEXT    NOT NULL UNIQUE,
    nombre    TEXT    NOT NULL,
    creado    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS chequeos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sitio_id    INTEGER NOT NULL REFERENCES sitios(id) ON DELETE CASCADE,
    estado      TEXT    NOT NULL CHECK (estado IN ('OK', 'LENTO', 'ERROR')),
    codigo_http INTEGER,
    tiempo_ms   REAL,
    error       TEXT,
    fecha       TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chequeos_sitio_fecha ON chequeos (sitio_id, fecha);
CREATE INDEX IF NOT EXISTS idx_chequeos_fecha ON chequeos (fecha);
"""


def ahora_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conectar(db_path):
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def conexion(db_path):
    conn = _conectar(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def nombre_desde_url(url):
    from urllib.parse import urlparse

    host = urlparse(url).hostname or url
    return host[4:] if host.startswith("www.") else host


def init_db(db_path, sitios_iniciales=()):
    with conexion(db_path) as c:
        c.execute("PRAGMA journal_mode = WAL")
        c.executescript(ESQUEMA)
        if c.execute("SELECT COUNT(*) FROM sitios").fetchone()[0] == 0:
            for url in sitios_iniciales:
                c.execute(
                    "INSERT OR IGNORE INTO sitios (url, nombre, creado) VALUES (?, ?, ?)",
                    (url, nombre_desde_url(url), iso(ahora_utc())),
                )


# ---------------------------------------------------------------- sitios

def listar_sitios(db_path):
    with conexion(db_path) as c:
        return [dict(r) for r in c.execute("SELECT * FROM sitios ORDER BY id")]


def agregar_sitio(db_path, url, nombre=None):
    nombre = (nombre or "").strip() or nombre_desde_url(url)
    try:
        with conexion(db_path) as c:
            cur = c.execute(
                "INSERT INTO sitios (url, nombre, creado) VALUES (?, ?, ?)",
                (url, nombre[:80], iso(ahora_utc())),
            )
            return {"id": cur.lastrowid, "url": url, "nombre": nombre[:80]}
    except sqlite3.IntegrityError:
        raise ValueError("Ese sitio ya está siendo monitoreado") from None


def eliminar_sitio(db_path, sitio_id):
    with conexion(db_path) as c:
        return c.execute("DELETE FROM sitios WHERE id = ?", (sitio_id,)).rowcount > 0


# ---------------------------------------------------------------- chequeos

def registrar_chequeo(db_path, sitio_id, resultado, fecha=None):
    with conexion(db_path) as c:
        c.execute(
            """INSERT INTO chequeos (sitio_id, estado, codigo_http, tiempo_ms, error, fecha)
               SELECT ?, ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM sitios WHERE id = ?)""",
            (
                sitio_id,
                resultado.estado,
                resultado.codigo_http,
                resultado.tiempo_ms,
                resultado.error,
                iso(fecha or ahora_utc()),
                sitio_id,
            ),
        )


def purgar_antiguos(db_path, dias):
    limite = iso(ahora_utc() - timedelta(days=dias))
    with conexion(db_path) as c:
        return c.execute("DELETE FROM chequeos WHERE fecha < ?", (limite,)).rowcount


def resumen(db_path, puntos_serie=30):
    """Estado actual de cada sitio + estadísticas de las últimas 24 h."""
    desde = iso(ahora_utc() - timedelta(hours=24))
    with conexion(db_path) as c:
        sitios = [dict(r) for r in c.execute("SELECT id, url, nombre FROM sitios ORDER BY id")]
        ultimos = {
            r["sitio_id"]: dict(r)
            for r in c.execute(
                """SELECT ch.* FROM chequeos ch
                   JOIN (SELECT sitio_id, MAX(id) AS max_id FROM chequeos GROUP BY sitio_id) u
                     ON ch.id = u.max_id"""
            )
        }
        stats = {
            r["sitio_id"]: dict(r)
            for r in c.execute(
                """SELECT sitio_id,
                          COUNT(*) AS total,
                          SUM(CASE WHEN estado != 'ERROR' THEN 1 ELSE 0 END) AS arriba,
                          AVG(CASE WHEN estado != 'ERROR' THEN tiempo_ms END) AS promedio
                   FROM chequeos WHERE fecha >= ? GROUP BY sitio_id""",
                (desde,),
            )
        }
        for s in sitios:
            u = ultimos.get(s["id"])
            st = stats.get(s["id"])
            s["estado"] = u["estado"] if u else "SIN_DATOS"
            s["codigo_http"] = u["codigo_http"] if u else None
            s["tiempo_ms"] = round(u["tiempo_ms"], 1) if u and u["tiempo_ms"] is not None else None
            s["error"] = u["error"] if u else None
            s["fecha"] = u["fecha"] if u else None
            s["chequeos_24h"] = st["total"] if st else 0
            s["uptime_24h"] = round(100 * st["arriba"] / st["total"], 2) if st else None
            s["promedio_ms_24h"] = (
                round(st["promedio"], 1) if st and st["promedio"] is not None else None
            )
            filas = c.execute(
                """SELECT estado, tiempo_ms, fecha FROM chequeos
                   WHERE sitio_id = ? ORDER BY id DESC LIMIT ?""",
                (s["id"], puntos_serie),
            ).fetchall()
            s["serie"] = [
                {"t": f["fecha"], "ms": f["tiempo_ms"], "estado": f["estado"]}
                for f in reversed(filas)
            ]
    return sitios


def serie(db_path, sitio_id, limite=120):
    with conexion(db_path) as c:
        filas = c.execute(
            """SELECT estado, codigo_http, tiempo_ms, error, fecha FROM chequeos
               WHERE sitio_id = ? ORDER BY id DESC LIMIT ?""",
            (sitio_id, limite),
        ).fetchall()
    return [dict(f) for f in reversed(filas)]


def historial(db_path, sitio_id=None, estado=None, limite=50, offset=0):
    condiciones, params = [], []
    if sitio_id is not None:
        condiciones.append("ch.sitio_id = ?")
        params.append(sitio_id)
    if estado:
        condiciones.append("ch.estado = ?")
        params.append(estado)
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    with conexion(db_path) as c:
        total = c.execute(f"SELECT COUNT(*) FROM chequeos ch {where}", params).fetchone()[0]
        filas = c.execute(
            f"""SELECT ch.id, ch.sitio_id, s.nombre, s.url, ch.estado, ch.codigo_http,
                       ch.tiempo_ms, ch.error, ch.fecha
                FROM chequeos ch JOIN sitios s ON s.id = ch.sitio_id
                {where} ORDER BY ch.id DESC LIMIT ? OFFSET ?""",
            params + [limite, offset],
        ).fetchall()
    return [dict(f) for f in filas], total
