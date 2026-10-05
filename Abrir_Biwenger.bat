@echo off
REM ============================================================
REM  Lanzador de la app Biwenger 26/27
REM  Se ejecuta desde la carpeta donde esta este archivo
REM ============================================================

cd /d "%~dp0"

REM Si usas un entorno virtual (venv), descomenta la siguiente linea
REM y pon la ruta a tu entorno:
REM call venv\Scripts\activate.bat

streamlit run app.py

pause
