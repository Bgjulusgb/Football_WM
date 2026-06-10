# start.ps1 — RedditOrakel Ein-Klick-Launcher.
# Konsole zeigt nur kurze Statuszeilen. Alles Detail-Logging geht in setup.log.
# Nach erfolgreichem Start oeffnet sich das Dashboard automatisch im Browser.

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }

$backendDir  = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$venvPy      = Join-Path $backendDir ".venv\Scripts\python.exe"
$venvPip     = Join-Path $backendDir ".venv\Scripts\pip.exe"
$reqFile     = Join-Path $backendDir "requirements.txt"
$envFile     = Join-Path $backendDir ".env"
$logFile     = Join-Path $root "setup.log"
$dashboard   = "http://localhost:5173"

"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] RedditOrakel Setup gestartet" | Out-File -Encoding utf8 $logFile

function Step([string]$label, [scriptblock]$action) {
    $padded = ($label + " " * 22).Substring(0, 22)
    Write-Host -NoNewline "  $padded "
    $result = & $action
    switch ($result) {
        "OK"      { Write-Host "OK"      -ForegroundColor Green }
        "NEU"     { Write-Host "NEU"     -ForegroundColor Cyan }
        "SKIP"    { Write-Host "SKIP"    -ForegroundColor DarkGray }
        "WARNUNG" { Write-Host "WARNUNG" -ForegroundColor Yellow; $script:setupWarn = $true }
        "FEHLT"   { Write-Host "FEHLT"   -ForegroundColor Red; $script:setupFail = $true }
        default   { Write-Host $result }
    }
}

function Append([string]$msg) {
    Add-Content -Path $logFile -Encoding utf8 -Value $msg
}

$script:setupWarn = $false
$script:setupFail = $false

Write-Host ""
Write-Host "  RedditOrakel wird vorbereitet ..." -ForegroundColor White
Write-Host "  (Details in setup.log, falls etwas schiefgeht)" -ForegroundColor DarkGray
Write-Host ""

Step "Python" {
    if (Test-Path $venvPy) { return "OK" }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Append "[python] nicht gefunden — Python 3.11+ von https://www.python.org/downloads/ installieren"
        return "FEHLT"
    }
    return "OK"
}

if ($script:setupFail) { exit 1 }

Step "venv" {
    if (Test-Path $venvPy) { return "OK" }
    python -m venv (Join-Path $backendDir ".venv") *>> $logFile
    if (-not (Test-Path $venvPy)) { Append "[venv] Erstellung fehlgeschlagen"; return "FEHLT" }
    & $venvPy -m pip install --quiet --upgrade pip *>> $logFile
    return "NEU"
}

if ($script:setupFail) { exit 1 }

Step "Backend-Pakete" {
    if (-not (Test-Path $reqFile)) { return "SKIP" }
    & $venvPip install --quiet --upgrade -r $reqFile *>> $logFile
    if ($LASTEXITCODE -ne 0) { return "WARNUNG" }
    return "OK"
}

Step "Sprach-Modell" {
    & $venvPy -c "import en_core_web_sm" 2>$null
    if ($LASTEXITCODE -eq 0) { return "OK" }
    & $venvPy -m spacy download en_core_web_sm --quiet *>> $logFile
    if ($LASTEXITCODE -ne 0) { return "WARNUNG" }
    return "NEU"
}

Step "Konfiguration" {
    if (Test-Path $envFile) { return "OK" }
    @(
        "USE_MOCK_CRAWLER=false",
        "USE_ARCTIC_SHIFT=true",
        "USE_ROBERTA=false",
        "USE_FACTOR_ENSEMBLE=true",
        "GOAL_MODEL=poisson",
        "DATABASE_URL=sqlite+aiosqlite:///./redditorakel.db",
        "LOG_LEVEL=INFO",
        "USE_NVIDIA_LLM=false",
        "ADMIN_API_KEY="
    ) | Set-Content -Encoding utf8 $envFile
    return "NEU"
}

Step "Dashboard-Pakete" {
    if (-not (Test-Path (Join-Path $frontendDir "package.json"))) { return "SKIP" }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Append "[npm] nicht gefunden — Node.js 18+ von https://nodejs.org/ installieren"
        return "FEHLT"
    }
    if (Test-Path (Join-Path $frontendDir "node_modules")) { return "OK" }
    Push-Location $frontendDir
    try {
        if (Test-Path "package-lock.json") { npm ci --silent *>> $logFile }
        else { npm install --silent *>> $logFile }
        if ($LASTEXITCODE -ne 0) { return "WARNUNG" }
        return "NEU"
    } finally { Pop-Location }
}

Write-Host ""
if ($script:setupFail) {
    Write-Host "  [FEHLER] Setup abgebrochen. Schau in setup.log fuer Details." -ForegroundColor Red
    Write-Host ""
    Read-Host "  Druecke ENTER um zu schliessen"
    exit 1
}
if ($script:setupWarn) {
    Write-Host "  [Hinweis] Setup mit Warnungen abgeschlossen — siehe setup.log" -ForegroundColor Yellow
} else {
    Write-Host "  Setup fertig." -ForegroundColor White
}
Write-Host ""

# Backend in eigenem Fenster starten
$backendHelper = Join-Path $root "_run-backend.ps1"
if (-not (Test-Path $backendHelper)) {
    Write-Host "  [FEHLER] _run-backend.ps1 fehlt." -ForegroundColor Red
    Read-Host "  Druecke ENTER um zu schliessen"
    exit 1
}
Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-File",$backendHelper | Out-Null

# Frontend in eigenem Fenster starten (falls vorhanden)
$frontendHelper = Join-Path $root "_run-frontend.ps1"
if ((Test-Path (Join-Path $frontendDir "package.json")) -and (Test-Path $frontendHelper)) {
    Start-Process powershell -ArgumentList "-NoExit","-ExecutionPolicy","Bypass","-File",$frontendHelper | Out-Null
} else {
    Write-Host "  [Hinweis] Frontend wird nicht gestartet (kein Helper-Skript)." -ForegroundColor Yellow
}

# Browser auf Dashboard, sobald Vite oben ist
Start-Sleep -Seconds 6
Start-Process $dashboard | Out-Null

Write-Host "  Dashboard:  $dashboard"           -ForegroundColor Cyan
Write-Host "  Backend:    http://localhost:8000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Beide Service-Fenster bleiben offen. Schliesse sie, um zu beenden." -ForegroundColor White
Write-Host "  Dieses Fenster kannst du mit ENTER schliessen."                      -ForegroundColor DarkGray
Read-Host ""
exit 0
