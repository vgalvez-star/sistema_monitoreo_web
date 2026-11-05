"""Punto de entrada.

Producción (Render):  gunicorn aplicacion_web_monitoreo:app
Desarrollo local:     python aplicacion_web_monitoreo.py
                      (agrega --abrir para abrir el navegador automáticamente)
"""

import os
import sys
import threading
import webbrowser

from monitoreo import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    puerto = int(os.environ.get("PORT", "5000"))
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{puerto}"

    print(f"\n  Panel disponible en {url}")
    print("  Usuario: admin   Contraseña: admin123 (o la definida en ADMIN_PASSWORD)")
    print("  Para detenerlo presiona Ctrl+C\n")

    if "--abrir" in sys.argv:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()

    app.run(
        host=host,
        port=puerto,
        debug=os.environ.get("FLASK_DEBUG") == "1",
        use_reloader=False,
    )
