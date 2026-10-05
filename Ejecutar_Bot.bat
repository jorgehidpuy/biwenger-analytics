@echo off
REM ============================================================
REM  Lanzador del bot de Biwenger.
REM  Pensado para el Programador de tareas: nunca se queda esperando
REM  a que alguien pulse una tecla, y deja rastro de TODO en
REM  ejecucion_tarea.log, incluso de lo que pasa antes de que el
REM  propio bot empiece a escribir su bot_diario.log.
REM ============================================================

cd /d "%~dp0"
set LANZADOR=ejecucion_tarea.log

echo. >> "%LANZADOR%"
echo [%date% %time%] --- lanzando bot_diario.py --- >> "%LANZADOR%"

REM Si python no esta en el PATH del usuario que ejecuta la tarea, el bot
REM ni siquiera arranca y su log se queda igual que estaba. Por eso se
REM comprueba aqui: es el fallo mas comun de una tarea programada.
where python >nul 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERROR: no encuentro python en el PATH. >> "%LANZADOR%"
    echo    Prueba a poner la ruta completa, por ejemplo: >> "%LANZADOR%"
    echo    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" bot_diario.py >> "%LANZADOR%"
    exit /b 1
)

python bot_diario.py >> "%LANZADOR%" 2>&1
set CODIGO=%errorlevel%

if %CODIGO% neq 0 (
    echo [%date% %time%] TERMINO CON FALLO, codigo %CODIGO% >> "%LANZADOR%"
) else (
    echo [%date% %time%] terminado correctamente >> "%LANZADOR%"
)

exit /b %CODIGO%
