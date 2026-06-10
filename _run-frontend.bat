@echo off
chcp 65001 >nul 2>&1
title RedditOrakel Frontend (vite :5173)

set "ROOT=%~dp0"
set "FRONTEND=%ROOT%frontend"

if not exist "%FRONTEND%\package.json" (
    echo.
    echo  [FEHLER] Frontend nicht gefunden:
    echo           "%FRONTEND%\package.json"
    echo.
    pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [FEHLER] npm nicht gefunden im PATH.
    echo           Bitte Node.js 18+ installieren: https://nodejs.org/
    echo.
    pause
    exit /b 1
)

cd /d "%FRONTEND%"

echo.
echo  ==================================================================
echo   RedditOrakel Frontend (React / Vite)
echo   URL    :  http://localhost:5173
echo   Admin  :  http://localhost:5173/admin
echo  ==================================================================
echo.
echo  Fenster manuell schliessen wenn fertig.
echo.

call npm run dev
set "RC=%ERRORLEVEL%"

echo.
echo  ------------------------------------------------------------------
if "%RC%"=="0" (
    echo  Frontend regulaer beendet.
) else (
    echo  [FEHLER] Frontend wurde mit Exit-Code %RC% beendet.
    echo           Pruefe oben stehende Meldungen.
)
echo.
pause
exit /b %RC%
