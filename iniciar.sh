#!/usr/bin/env bash
# Inicia el Sistema de Monitoreo Web en macOS o Linux: ./iniciar.sh
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "No se encontró python3. Instálalo y vuelve a intentarlo."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Preparando el entorno por primera vez, espera un momento..."
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
exec .venv/bin/python aplicacion_web_monitoreo.py --abrir
