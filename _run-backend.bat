@echo off
chcp 65001 >nul 2>&1
title RedditOrakel Backend (uvicorn :8000)

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo.
    echo  [FEHLER] Python venv nicht gefunden:
    echo           "%VENV_PY%"
    echo.
    echo  Bitte zuerst start.bat ausfuehren ^(legt venv an und installiert Deps^).
    echo.
    pause
    exit /b 1
)

if not exist "%BACKEND%\main.py" (
    echo.
    echo  [FEHLER] Backend-Hauptmodul fehlt:
    echo           "%BACKEND%\main.py"
    echo.
    pause
    exit /b 1
)

cd /d "%BACKEND%"

echo.
echo  ==================================================================
echo   RedditOrakel Backend (FastAPI / uvicorn)
echo   URL    :  http://localhost:8000
echo   Swagger:  http://localhost:8000/docs
echo  ==================================================================
echo.
echo  Fenster manuell schliessen wenn fertig.
echo.

"%VENV_PY%" -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
set "RC=%ERRORLEVEL%"

echo.
echo  ------------------------------------------------------------------
if "%RC%"=="0" (
    echo  Backend regulaer beendet.
) else (
    echo  [FEHLER] Backend wurde mit Exit-Code %RC% beendet.
    echo           Pruefe oben stehende Meldungen.
)
echo.
pause
exit /b %RC%
