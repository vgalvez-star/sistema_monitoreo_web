"""Punto de entrada.

Producción (Render):  gunicorn aplicacion_web_monitoreo:app
Desarrollo local:     python aplicacion_web_monitoreo.py
"""

import os

from monitoreo import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
        use_reloader=False,
    )
