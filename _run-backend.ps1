# _run-backend.ps1 -- Standalone Backend-Launcher (von start.ps1 aufgerufen)
$ErrorActionPreference = "Continue"

$root        = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }
$backendDir  = Join-Path $root "backend"
$venvAct     = Join-Path $backendDir ".venv\Scripts\Activate.ps1"
$venvPy      = Join-Path $backendDir ".venv\Scripts\python.exe"

try { $Host.UI.RawUI.WindowTitle = "RedditOrakel Backend (uvicorn :8000)" } catch {}

if (-not (Test-Path $venvPy)) {
    Write-Host ""
    Write-Host "  [FEHLER] Python venv nicht gefunden:" -ForegroundColor Red
    Write-Host "           $venvPy" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Bitte zuerst start.ps1 ausfuehren (legt venv an und installiert Deps)." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  ENTER zum Schliessen"
    exit 1
}

if (-not (Test-Path (Join-Path $backendDir "main.py"))) {
    Write-Host ""
    Write-Host "  [FEHLER] Backend-Hauptmodul fehlt: $backendDir\main.py" -ForegroundColor Red
    Write-Host ""
    Read-Host "  ENTER zum Schliessen"
    exit 1
}

Set-Location $backendDir
if (Test-Path $venvAct) { & $venvAct }

Write-Host ""
Write-Host "  ==================================================================" -ForegroundColor Cyan
Write-Host "   RedditOrakel Backend (FastAPI / uvicorn)" -ForegroundColor Cyan
Write-Host "   URL    :  http://localhost:8000" -ForegroundColor Cyan
Write-Host "   Swagger:  http://localhost:8000/docs" -ForegroundColor DarkGray
Write-Host "  ==================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Fenster manuell schliessen wenn fertig." -ForegroundColor DarkGray
Write-Host ""

$rc = 1
try {
    & $venvPy -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
    $rc = $LASTEXITCODE
} catch {
    Write-Host ""
    Write-Host "  [FEHLER] Backend Exception:" -ForegroundColor Red
    Write-Host "  $_" -ForegroundColor Red
    $rc = 1
}

Write-Host ""
Write-Host "  ------------------------------------------------------------------" -ForegroundColor DarkGray
if ($rc -eq 0) {
    Write-Host "  Backend regulaer beendet." -ForegroundColor Green
} else {
    Write-Host "  [FEHLER] Backend Exit-Code: $rc" -ForegroundColor Red
    Write-Host "           Pruefe oben stehende Meldungen." -ForegroundColor Yellow
}
Write-Host ""
Read-Host "  ENTER zum Schliessen"
exit $rc
