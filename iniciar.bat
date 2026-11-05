@echo off
title Sistema de Monitoreo Web
cd /d "%~dp0"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>nul || (
  echo.
  echo  No se encontro Python. Instalalo desde https://www.python.org/downloads/
  echo  y marca la opcion "Add Python to PATH" durante la instalacion.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  Preparando el entorno por primera vez, espera un momento...
  %PY% -m venv .venv || (pause & exit /b 1)
)

".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (
  echo  No se pudieron instalar las dependencias. Revisa tu conexion a internet.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" aplicacion_web_monitoreo.py --abrir
pause
