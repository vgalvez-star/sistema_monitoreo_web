from flask import Flask, render_template_string, jsonify, request
import threading
import time
import requests
from datetime import datetime
import sqlite3

app = Flask(__name__)

# ==============================
# BASE DE DATOS
# ==============================

def init_db():
    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS monitoreo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        web TEXT,
        status TEXT,
        tiempo REAL,
        fecha TEXT
    )
    """)

    conn.commit()
    conn.close()

# ==============================
# WEBS A MONITOREAR
# ==============================

websites = [
    "https://www.google.com",
    "https://qqqq234.com"
]

# ==============================
# DICCIONARIOS
# ==============================

data = {
    web: {
        "status": "N/A",
        "tiempo": 0,
        "hora": "-"
    }
    for web in websites
}

historial = {
    web: []
    for web in websites
}

# ==============================
# LOGIN SIMPLE
# ==============================

usuario = "admin"
password = "1234"

# ==============================
# FUNCION DE CHEQUEO
# ==============================

def check_web(url):
    try:
        start = time.time()

        response = requests.get(url, timeout=5)

        tiempo = round(time.time() - start, 2)

        if response.status_code == 200:
            return "OK", tiempo
        else:
            return "ERROR", tiempo

    except:
        return "ERROR", None

# ==============================
# MONITOREO
# ==============================

def monitor():

    conn = sqlite3.connect("monitor.db", check_same_thread=False)
    cursor = conn.cursor()

    while True:

        for web in websites:

            status, tiempo = check_web(web)

            data[web] = {
                "status": status,
                "tiempo": tiempo if tiempo is not None else 0,
                "hora": datetime.now().strftime("%H:%M:%S")
            }

            # HISTORIAL
            if tiempo is not None:

                historial[web].append(tiempo)

                if len(historial[web]) > 10:
                    historial[web].pop(0)

            # GUARDAR EN SQLITE
            cursor.execute(
                """
                INSERT INTO monitoreo (web, status, tiempo, fecha)
                VALUES (?, ?, ?, ?)
                """,
                (
                    web,
                    status,
                    tiempo if tiempo is not None else 0,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )

            conn.commit()

        time.sleep(5)

# ==============================
# INICIAR HILO (IMPORTANTE PARA RENDER)
# ==============================

init_db()

hilo = threading.Thread(target=monitor)
hilo.daemon = True
hilo.start()

# ==============================
# API STATUS
# ==============================

@app.route("/api/status")
def api_status():
    return jsonify(data)

# ==============================
# API HISTORIAL
# ==============================

@app.route("/api/historial")
def api_historial():

    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT web, status, tiempo, fecha
    FROM monitoreo
    ORDER BY id DESC
    LIMIT 20
    """)

    datos = cursor.fetchall()

    conn.close()

    resultado = []

    for row in datos:

        resultado.append({
            "web": row[0],
            "status": row[1],
            "tiempo": row[2],
            "fecha": row[3]
        })

    return jsonify(resultado)

# ==============================
# LOGIN
# ==============================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        user = request.form["username"]
        pwd = request.form["password"]

        if user == usuario and pwd == password:
            return "LOGIN CORRECTO"

        else:
            return "CREDENCIALES INCORRECTAS"

    return """
    <h2>Login</h2>

    <form method="POST">

        Usuario:
        <input name="username">

        <br><br>

        Password:
        <input name="password" type="password">

        <br><br>

        <button type="submit">
            Entrar
        </button>

    </form>
    """

# ==============================
# HISTORIAL HTML
# ==============================

@app.route("/historial")
def ver_historial():

    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT web, status, tiempo, fecha
    FROM monitoreo
    ORDER BY id DESC
    LIMIT 20
    """)

    datos = cursor.fetchall()

    conn.close()

    html = """
    <h1>📜 Historial</h1>

    <table border="1" cellpadding="10">

        <tr>
            <th>Web</th>
            <th>Status</th>
            <th>Tiempo</th>
            <th>Fecha</th>
        </tr>

        {% for row in datos %}

        <tr>
            <td>{{ row[0] }}</td>
            <td>{{ row[1] }}</td>
            <td>{{ row[2] }}</td>
            <td>{{ row[3] }}</td>
        </tr>

        {% endfor %}

    </table>
    """

    return render_template_string(html, datos=datos)

# ==============================
# DASHBOARD
# ==============================

@app.route("/")
def dashboard():

    web_principal = websites[0]

    html = """
<!DOCTYPE html>

<html>

<head>

    <title>Monitor de Red</title>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

    <meta http-equiv="refresh" content="5">

</head>

<body>

<h1>📊 Monitor de Red</h1>

<table border="1" cellpadding="10">

    <tr>
        <th>Web</th>
        <th>Estado</th>
        <th>Tiempo</th>
        <th>Hora</th>
    </tr>

    {% for web, info in data.items() %}

    <tr>

        <td>{{ web }}</td>

        <td style="color: {{ 'green' if info.status == 'OK' else 'red' }}">
            {{ info.status }}
        </td>

        <td>{{ info.tiempo }}</td>

        <td>{{ info.hora }}</td>

    </tr>

    {% endfor %}

</table>

<h2>📈 Tiempo de Respuesta</h2>

<canvas id="chart" width="400" height="200"></canvas>

<script>

const ctx = document.getElementById('chart').getContext('2d');

const chart = new Chart(ctx, {

    type: 'line',

    data: {

        labels: {{ historial[web_principal]|tojson }},

        datasets: [{

            label: 'Tiempo (s)',

            data: {{ historial[web_principal]|tojson }},

            borderWidth: 2

        }]
    }
});

</script>

</body>
</html>
"""

    return render_template_string(
        html,
        data=data,
        historial=historial,
        web_principal=web_principal
    )

# ==============================
# MAIN
# ==============================

if __name__ == "__main__":
    app.run(debug=True)
