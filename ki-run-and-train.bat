@echo off
chcp 65001 >nul 2>&1
title RedditOrakel v3.5 - KI Run and Train
setlocal EnableDelayedExpansion
color 0A

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"
set "VENV_PIP=%BACKEND%\.venv\Scripts\pip.exe"

REM ----- Mode aus Argumenten parsen -----
set "MODE_ARG="
for %%a in (%*) do (
    set "ARG=%%a"
    if "!ARG:~0,7!"=="--mode=" set "MODE_ARG=!ARG:~7!"
)
if /I "%MODE_ARG%"=="run" (
    echo.
    echo  ==================================================================
    echo  [Hinweis] --mode=run wird seit v3.5 NICHT mehr unterstuetzt.
    echo            Verwende stattdessen:  start.bat
    echo            ^(Backend + Frontend in eigenen Fenstern, ohne ML-Stack^)
    echo  ==================================================================
    echo.
    endlocal
    pause
    exit /b 1
)
if /I "%MODE_ARG%"=="train" set "PASS_MODE=--mode=train"
if /I "%MODE_ARG%"=="menu"  set "PASS_MODE=--mode=menu"
if not defined PASS_MODE    set "PASS_MODE=--mode=auto"

echo.
echo  ==================================================================
echo            RedditOrakel v3.5 - KI Run and Train
echo    18-Faktor-Ensemble  ^|  Dixon-Coles / NegBin / GLM  ^|  PyMC
echo  ==================================================================
echo.
echo  Dieser Launcher trainiert Modelle / oeffnet das Verwaltungsmenue.
echo  Fuer normalen App-Start (Dashboard + Backend): start.bat
echo.

call :step_find_python      || goto :failed
call :step_ensure_venv      || goto :failed
call :step_ensure_gpp
call :step_core_deps
call :step_scientific_stack
call :step_spacy_model
call :step_frontend_deps

echo.
echo  [Setup abgeschlossen] Starte ki_runner %PASS_MODE% ...
echo  ------------------------------------------------------------------
echo.

cd /d "%BACKEND%"
"%VENV_PY%" -m scripts.ki_runner %PASS_MODE%
set "RC=%ERRORLEVEL%"

echo.
echo  ------------------------------------------------------------------
echo  ki-run-and-train beendet (Exit %RC%).
endlocal
pause
exit /b %RC%

:failed
echo.
echo  [Setup fehlgeschlagen] Bitte oben stehende Meldungen pruefen.
endlocal
pause
exit /b 1

REM =================================================================
REM Subroutinen
REM =================================================================

:step_find_python
if exist "%VENV_PY%" (
    echo  [1/7] Python: venv vorhanden
    exit /b 0
)
where python >nul 2>&1
if errorlevel 1 (
    echo  [FEHLER] Python nicht gefunden. Bitte Python 3.11+ installieren.
    echo           https://www.python.org/downloads/
    exit /b 1
)
echo  [1/7] Python: System-Python gefunden
exit /b 0

:step_ensure_venv
if exist "%VENV_PY%" (
    echo  [2/7] venv vorhanden
    exit /b 0
)
echo  [2/7] Erstelle virtuelles Environment ...
python -m venv "%BACKEND%\.venv"
if errorlevel 1 (
    echo  [FEHLER] venv-Erstellung fehlgeschlagen.
    exit /b 1
)
"%VENV_PY%" -m pip install --quiet --upgrade pip
echo        venv erstellt.
exit /b 0

:step_ensure_gpp
where g++ >nul 2>&1
if not errorlevel 1 (
    echo  [3/7] g++: vorhanden
    exit /b 0
)
if exist "C:\msys64\ucrt64\bin\g++.exe" (
    set "PATH=C:\msys64\ucrt64\bin;%PATH%"
    echo  [3/7] g++: gefunden unter C:\msys64\ucrt64\bin
    exit /b 0
)
echo  [3/7] g++: nicht gefunden - rufe install-mingw.ps1 auf ...
if exist "%ROOT%install-mingw.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%install-mingw.ps1" -Quiet
    if exist "C:\msys64\ucrt64\bin\g++.exe" (
        set "PATH=C:\msys64\ucrt64\bin;%PATH%"
        echo        g++ installiert.
        exit /b 0
    )
)
echo        [WARNUNG] g++ nicht installiert - PyTensor laeuft im Python-Mode (langsamer).
echo                  Manuelle Installation: .\install-mingw.ps1
set "PYTENSOR_FLAGS=mode=FAST_COMPILE,cxx="
exit /b 0

:step_core_deps
if not exist "%BACKEND%\requirements.txt" (
    echo  [4/7] requirements.txt fehlt - uebersprungen.
    exit /b 0
)
echo  [4/7] Installiere Core-Dependencies (requirements.txt) ...
"%VENV_PIP%" install --upgrade -r "%BACKEND%\requirements.txt" --quiet
if errorlevel 1 (
    echo        [WARNUNG] Einige Core-Pakete konnten nicht installiert werden.
) else (
    echo        Core-Dependencies aktuell.
)
exit /b 0

:step_scientific_stack
echo  [5/7] Installiere Scientific Stack (LightGBM, Optuna, PyMC, ArviZ, Prefect) ...
"%VENV_PIP%" install --upgrade lightgbm optuna pymc arviz prefect trafilatura --quiet
if errorlevel 1 (
    echo        [WARNUNG] Einige Scientific-Pakete konnten nicht installiert werden.
) else (
    echo        Scientific Stack installiert.
)
exit /b 0

:step_spacy_model
echo  [6/7] Pruefe spaCy-Modell (en_core_web_sm) ...
"%VENV_PY%" -c "import en_core_web_sm" >nul 2>&1
if errorlevel 1 (
    echo        Lade spaCy-Modell herunter ...
    "%VENV_PY%" -m spacy download en_core_web_sm --quiet
    if errorlevel 1 (
        echo        [WARNUNG] spaCy-Modell konnte nicht geladen werden.
    ) else (
        echo        spaCy-Modell installiert.
    )
) else (
    echo        spaCy-Modell vorhanden.
)
exit /b 0

:step_frontend_deps
if not exist "%FRONTEND%\package.json" (
    echo  [7/7] Kein Frontend gefunden - uebersprungen.
    exit /b 0
)
where npm >nul 2>&1
if errorlevel 1 (
    echo  [7/7] npm nicht gefunden - Frontend-Deps uebersprungen.
    exit /b 0
)
if exist "%FRONTEND%\node_modules" (
    echo  [7/7] Frontend-Deps vorhanden.
    exit /b 0
)
echo  [7/7] Installiere Frontend-Dependencies ...
pushd "%FRONTEND%"
if exist "package-lock.json" (
    npm ci --silent 2>nul
) else (
    npm install --silent 2>nul
)
popd
echo        Frontend-Dependencies installiert.
exit /b 0
