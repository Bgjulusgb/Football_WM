# _run-frontend.ps1 -- Standalone Frontend-Launcher (von start.ps1 aufgerufen)
$ErrorActionPreference = "Continue"

$root        = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }
$frontendDir = Join-Path $root "frontend"

try { $Host.UI.RawUI.WindowTitle = "RedditOrakel Frontend (vite :5173)" } catch {}

if (-not (Test-Path (Join-Path $frontendDir "package.json"))) {
    Write-Host ""
    Write-Host "  [FEHLER] Frontend nicht gefunden: $frontendDir\package.json" -ForegroundColor Red
    Write-Host ""
    Read-Host "  ENTER zum Schliessen"
    exit 1
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "  [FEHLER] npm nicht gefunden im PATH." -ForegroundColor Red
    Write-Host "           Bitte Node.js 18+ installieren: https://nodejs.org/" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  ENTER zum Schliessen"
    exit 1
}

Set-Location $frontendDir

Write-Host ""
Write-Host "  ==================================================================" -ForegroundColor Magenta
Write-Host "   RedditOrakel Frontend (React / Vite)" -ForegroundColor Magenta
Write-Host "   URL    :  http://localhost:5173" -ForegroundColor Magenta
Write-Host "   Admin  :  http://localhost:5173/admin" -ForegroundColor DarkGray
Write-Host "  ==================================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Fenster manuell schliessen wenn fertig." -ForegroundColor DarkGray
Write-Host ""

$rc = 1
try {
    npm run dev
    $rc = $LASTEXITCODE
} catch {
    Write-Host ""
    Write-Host "  [FEHLER] Frontend Exception:" -ForegroundColor Red
    Write-Host "  $_" -ForegroundColor Red
    $rc = 1
}

Write-Host ""
Write-Host "  ------------------------------------------------------------------" -ForegroundColor DarkGray
if ($rc -eq 0) {
    Write-Host "  Frontend regulaer beendet." -ForegroundColor Green
} else {
    Write-Host "  [FEHLER] Frontend Exit-Code: $rc" -ForegroundColor Red
    Write-Host "           Pruefe oben stehende Meldungen." -ForegroundColor Yellow
}
Write-Host ""
Read-Host "  ENTER zum Schliessen"
exit $rc
