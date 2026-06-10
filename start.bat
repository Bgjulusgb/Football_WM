@echo off
chcp 65001 >nul 2>&1
title RedditOrakel - Start
setlocal EnableDelayedExpansion
color 0A

REM ──────────────────────────────────────────────────────────────────────
REM  Ein-Klick-Launcher fuer RedditOrakel.
REM  Alles Setup-Geraeusch landet in setup.log — die Konsole bleibt ruhig.
REM  Fehlerfall: kurze Meldung + Verweis auf setup.log.
REM ──────────────────────────────────────────────────────────────────────

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"
set "VENV_PIP=%BACKEND%\.venv\Scripts\pip.exe"
set "LOG=%ROOT%setup.log"
set "DASHBOARD_URL=http://localhost:5173"

REM Log frisch anlegen
> "%LOG%" echo [%date% %time%] RedditOrakel Setup gestartet

echo.
echo   RedditOrakel wird vorbereitet ...
echo   (Details in setup.log, falls etwas schiefgeht)
echo.

call :setup_python      || goto :failed
call :setup_venv        || goto :failed
call :setup_pip         || set "SETUP_WARN=1"
call :setup_spacy       || set "SETUP_WARN=1"
call :setup_env_file
call :setup_frontend    || set "SETUP_WARN=1"

if defined SETUP_WARN (
    echo   [Hinweis] Setup mit Warnungen abgeschlossen — siehe setup.log
) else (
    echo   Setup fertig.
)
echo.

REM Backend starten ──────────────────────────────────────────────────────
if not exist "%ROOT%_run-backend.bat" (
    echo   [FEHLER] _run-backend.bat fehlt - bitte aus dem Repo nachziehen.
    goto :failed
)
start "RedditOrakel Backend" "%ROOT%_run-backend.bat"

REM Frontend starten ─────────────────────────────────────────────────────
if exist "%FRONTEND%\package.json" if exist "%ROOT%_run-frontend.bat" (
    start "RedditOrakel Frontend" "%ROOT%_run-frontend.bat"
) else (
    echo   [Hinweis] Frontend wird nicht gestartet ^(kein _run-frontend.bat^).
)

REM Dashboard im Browser oeffnen, sobald Frontend hochfaehrt ─────────────
timeout /t 6 /nobreak >nul
start "" "%DASHBOARD_URL%"

echo   Dashboard:  %DASHBOARD_URL%
echo   Backend:    http://localhost:8000
echo.
echo   Beide Service-Fenster bleiben offen. Schliesse sie, um zu beenden.
echo   Dieses Fenster kannst du mit ENTER schliessen.
echo.
endlocal
pause >nul
exit /b 0


:failed
echo.
echo   [FEHLER] Setup abgebrochen. Schau in setup.log fuer Details.
echo.
endlocal
pause
exit /b 1


REM ──────────────────────────────────────────────────────────────────────
REM  Setup-Subroutinen (alles ueber 1>>"%LOG%" 2>&1 in setup.log)
REM ──────────────────────────────────────────────────────────────────────

:setup_python
<nul set /p ".=  Python ............ "
if exist "%VENV_PY%" (
    echo OK ^(venv vorhanden^)
    exit /b 0
)
where python >nul 2>&1
if errorlevel 1 (
    echo FEHLT
    >>"%LOG%" echo [python] nicht gefunden
    >>"%LOG%" echo Installiere Python 3.11+ von https://www.python.org/downloads/
    exit /b 1
)
echo OK
>>"%LOG%" echo [python] System-Python gefunden
exit /b 0

:setup_venv
<nul set /p ".=  venv ............... "
if exist "%VENV_PY%" (
    echo OK
    exit /b 0
)
python -m venv "%BACKEND%\.venv" 1>>"%LOG%" 2>&1
if errorlevel 1 (
    echo FEHLT
    exit /b 1
)
"%VENV_PY%" -m pip install --quiet --upgrade pip 1>>"%LOG%" 2>&1
echo NEU
exit /b 0

:setup_pip
<nul set /p ".=  Backend-Pakete .... "
if not exist "%BACKEND%\requirements.txt" (
    echo SKIP
    exit /b 0
)
"%VENV_PIP%" install --upgrade -r "%BACKEND%\requirements.txt" --quiet 1>>"%LOG%" 2>&1
if errorlevel 1 (
    echo WARNUNG
    exit /b 1
)
echo OK
exit /b 0

:setup_spacy
<nul set /p ".=  Sprach-Modell ..... "
"%VENV_PY%" -c "import en_core_web_sm" >nul 2>&1
if not errorlevel 1 (
    echo OK
    exit /b 0
)
"%VENV_PY%" -m spacy download en_core_web_sm --quiet 1>>"%LOG%" 2>&1
if errorlevel 1 (
    echo WARNUNG
    exit /b 1
)
echo NEU
exit /b 0

:setup_env_file
<nul set /p ".=  Konfiguration ..... "
if exist "%BACKEND%\.env" (
    echo OK
    exit /b 0
)
(
    echo USE_MOCK_CRAWLER=false
    echo USE_ARCTIC_SHIFT=true
    echo USE_ROBERTA=false
    echo USE_FACTOR_ENSEMBLE=true
    echo GOAL_MODEL=poisson
    echo DATABASE_URL=sqlite+aiosqlite:///./redditorakel.db
    echo LOG_LEVEL=INFO
    echo USE_NVIDIA_LLM=false
    echo ADMIN_API_KEY=
) > "%BACKEND%\.env"
echo NEU
exit /b 0

:setup_frontend
<nul set /p ".=  Dashboard-Pakete . "
if not exist "%FRONTEND%\package.json" (
    echo SKIP
    exit /b 0
)
where npm >nul 2>&1
if errorlevel 1 (
    echo FEHLT
    >>"%LOG%" echo [npm] nicht gefunden — Node.js 18+ von https://nodejs.org/ installieren
    exit /b 1
)
if exist "%FRONTEND%\node_modules" (
    echo OK
    exit /b 0
)
pushd "%FRONTEND%"
if exist "package-lock.json" (
    call npm ci --silent 1>>"%LOG%" 2>&1
) else (
    call npm install --silent 1>>"%LOG%" 2>&1
)
set "NPM_RC=%ERRORLEVEL%"
popd
if not "%NPM_RC%"=="0" (
    echo WARNUNG
    exit /b 1
)
echo NEU
exit /b 0
