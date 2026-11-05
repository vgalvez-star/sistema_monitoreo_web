# Sistema de Monitoreo Web

Panel en Flask que chequea la disponibilidad y el tiempo de respuesta de sitios web, guarda el historial en SQLite y lo muestra en un dashboard con un **cielo animado que sigue la hora local**: el sol y la luna recorren el cielo, aparecen estrellas y se encienden las luces de la ciudad, y el saludo cambia según sea madrugada, mañana, tarde o noche.

## Funcionalidades

- **Monitoreo en segundo plano**: chequea todos los sitios en paralelo cada `CHECK_INTERVAL` segundos y los clasifica como **OK**, **LENTO** (sobre `SLOW_THRESHOLD_MS`) o **CAÍDO**, con el motivo concreto del fallo (timeout, DNS, SSL, HTTP 4xx/5xx).
- **Dashboard**: KPIs (servicios, operativos, incidencias, latencia media, disponibilidad 24 h), una tarjeta por sitio con sparkline, gráfico de tiempo de respuesta con umbral de lentitud y fallos marcados, y eventos recientes. Se actualiza solo cada 10 s y se pausa cuando la pestaña no está visible.
- **Cielo día/noche**: el saludo y el tema (claro de día, oscuro de noche) siguen la hora del equipo del visitante.

  | Momento | Horario | Saludo |
  |---|---|---|
  | Madrugada | 00:00 – 05:59 | Buena madrugada |
  | Mañana | 06:00 – 11:59 | Buenos días |
  | Tarde | 12:00 – 19:59 | Buenas tardes |
  | Noche | 20:00 – 23:59 | Buenas noches |

  Para probarlo sin esperar: `/?hora=22:30` fija la hora y `/?demo=1` recorre el día completo en unos 48 s. El botón **Auto / Claro / Oscuro** permite fijar un tema.
- **Gestión de sitios** desde la web: agregar y eliminar sin tocar el código.
- **Historial** paginado y filtrable por sitio y estado.
- **Seguridad**: login con sesión, contraseña desde variables de entorno (guardada como hash), protección CSRF, bloqueo temporal tras 5 intentos fallidos y redirecciones solo internas.

## Ejecutar en local

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export ADMIN_PASSWORD="una-clave-segura"     # Windows PowerShell: $env:ADMIN_PASSWORD="..."
python aplicacion_web_monitoreo.py
```

Abre <http://127.0.0.1:5000> e ingresa con el usuario `admin`. Si no defines `ADMIN_PASSWORD`, la aplicación genera una contraseña aleatoria, la muestra una vez en la consola y la guarda en `.admin_password` (ignorado por git).

## Despliegue en Render

El repositorio incluye `render.yaml`, así que puedes crear el servicio como **Blueprint**. Si prefieres configurarlo a mano:

- **Build command**: `pip install -r requirements.txt`
- **Start command**: `gunicorn aplicacion_web_monitoreo:app --workers 2 --threads 4 --timeout 60`
- **Health check path**: `/health`
- **Variables**: `ADMIN_PASSWORD`, `SECRET_KEY`, `TRUST_PROXY=1`, `SESSION_COOKIE_SECURE=1`

> El disco de Render en el plan gratuito se borra en cada despliegue o reinicio, y con él el historial. Para conservarlo, agrega un disco persistente y define `DB_PATH=/var/data/monitor.db`.

Aunque gunicorn levante varios workers, **solo uno ejecuta el monitoreo** (un candado de archivo junto a la base de datos lo garantiza), así que no se duplican los chequeos.

## Configuración

Todas las opciones se leen de variables de entorno; `.env.example` las lista con sus valores por defecto.

| Variable | Por defecto | Descripción |
|---|---|---|
| `ADMIN_USER` | `admin` | Usuario del panel |
| `ADMIN_PASSWORD` | aleatoria | Contraseña del panel |
| `SECRET_KEY` | aleatoria | Firma de las cookies de sesión |
| `MONITOR_SITES` | google.com, github.com | Sitios iniciales, separados por coma (solo si la base está vacía) |
| `CHECK_INTERVAL` | `15` | Segundos entre ciclos (mínimo 5) |
| `REQUEST_TIMEOUT` | `5` | Segundos antes de considerar un sitio caído |
| `SLOW_THRESHOLD_MS` | `1500` | Umbral para marcar un sitio como lento |
| `RETENTION_DAYS` | `7` | Días de historial que se conservan |
| `DB_PATH` | `monitor.db` | Ruta de la base SQLite |
| `TRUST_PROXY` | `0` | `1` detrás de un proxy HTTPS (Render, Nginx) |
| `SESSION_COOKIE_SECURE` | `0` | `1` para enviar la cookie solo por HTTPS |

## API

Todas las rutas `/api/*` requieren sesión iniciada. Las que modifican datos requieren además la cabecera `X-CSRF-Token`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/status` | Estado actual de cada sitio, estadísticas de 24 h y resumen |
| GET | `/api/serie/<id>?limite=120` | Últimos chequeos de un sitio |
| GET | `/api/historial?sitio=&estado=&limite=&offset=` | Historial paginado |
| POST | `/api/sitios` | Agrega un sitio: `{"url": "...", "nombre": "..."}` |
| DELETE | `/api/sitios/<id>` | Elimina un sitio y su historial |
| GET | `/health` | Comprobación pública para el balanceador |

## Estructura

```
aplicacion_web_monitoreo.py   punto de entrada (gunicorn / python)
monitoreo/
  __init__.py                 fábrica de la aplicación
  config.py                   configuración desde variables de entorno
  db.py                       acceso a SQLite
  checker.py                  chequeo HTTP con errores clasificados
  scheduler.py                bucle de monitoreo con candado entre procesos
  auth.py                     login, sesión y CSRF
  routes.py                   páginas y API
  templates/                  HTML (Jinja2)
  static/                     CSS, JS (cielo animado, panel) e ícono
tests/                        pruebas con pytest
```

## Pruebas

```bash
pip install pytest
python -m pytest
```
