# ki-run-and-train.ps1 -- RedditOrakel v3.5 ML/Training-Launcher (PowerShell)
# Setup (venv, pip, scientific stack, g++, spaCy, npm) + Modus-Auswahl (Train/Menu).
# Fuer normalen App-Start (Dashboard + Backend) bitte start.ps1 verwenden.

[CmdletBinding()]
param(
    [ValidateSet("train", "menu", "auto", "run")]
    [string]$Mode = "auto"
)

$ErrorActionPreference = "Continue"  # Fehler sichtbar, nicht throw

if ($Mode -eq "run") {
    Write-Host ""
    Write-Host "  ==================================================================" -ForegroundColor Yellow
    Write-Host "  [Hinweis] -Mode run wird seit v3.5 NICHT mehr unterstuetzt." -ForegroundColor Yellow
    Write-Host "            Verwende stattdessen:  .\start.ps1" -ForegroundColor Yellow
    Write-Host "            (Backend + Frontend in eigenen Fenstern, ohne ML-Stack)" -ForegroundColor Yellow
    Write-Host "  ==================================================================" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  Druecke ENTER zum Schliessen"
    exit 1
}
$root = $PSScriptRoot
if (-not $root) { $root = Split-Path -Parent $MyInvocation.MyCommand.Path }

$backendDir  = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$venvPy      = Join-Path $backendDir ".venv\Scripts\python.exe"
$venvPip     = Join-Path $backendDir ".venv\Scripts\pip.exe"
$reqFile     = Join-Path $backendDir "requirements.txt"

function Write-Step($num, $msg, $color = "Yellow") {
    Write-Host ("  [{0}/7] {1}" -f $num, $msg) -ForegroundColor $color
}

Write-Host ""
Write-Host "  ==================================================================" -ForegroundColor Cyan
Write-Host "            RedditOrakel v3.5 - KI Run and Train" -ForegroundColor Cyan
Write-Host "    18-Faktor-Ensemble  |  Dixon-Coles / NegBin / GLM  |  PyMC" -ForegroundColor Cyan
Write-Host "  ==================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Dieser Launcher trainiert Modelle / oeffnet das Verwaltungsmenue." -ForegroundColor White
Write-Host "  Fuer normalen App-Start (Dashboard + Backend): .\start.ps1" -ForegroundColor DarkGray
Write-Host ""

# -- 1/7 Python venv -----------------------------------------------------------
if (-not (Test-Path $venvPy)) {
    Write-Step 1 "venv wird erstellt ..."
    python -m venv (Join-Path $backendDir ".venv")
    & $venvPy -m pip install --quiet --upgrade pip
}
else {
    Write-Step 1 "venv vorhanden" "Green"
}

# -- 2/7 Core-Dependencies -----------------------------------------------------
Write-Step 2 "pip install -r requirements.txt ..."
& $venvPip install --quiet --upgrade -r $reqFile

# -- 3/7 g++ (PyTensor C-Backend) ---------------------------------------------
$gpp = Get-Command g++ -ErrorAction SilentlyContinue
if ($gpp) {
    Write-Step 3 "g++ vorhanden" "Green"
}
elseif (Test-Path "C:\msys64\ucrt64\bin\g++.exe") {
    $env:PATH = "C:\msys64\ucrt64\bin;$env:PATH"
    Write-Step 3 "g++ unter C:\msys64\ucrt64\bin gefunden" "Green"
}
else {
    Write-Step 3 "g++ fehlt -- rufe install-mingw.ps1 ..."
    $installScript = Join-Path $root "install-mingw.ps1"
    if (Test-Path $installScript) {
        & $installScript -Quiet
        if (Test-Path "C:\msys64\ucrt64\bin\g++.exe") {
            $env:PATH = "C:\msys64\ucrt64\bin;$env:PATH"
            Write-Host "        g++ installiert." -ForegroundColor Green
        }
        else {
            $env:PYTENSOR_FLAGS = "mode=FAST_COMPILE,cxx="
            Write-Host "        [WARNUNG] g++ nicht installiert -- Python-Mode aktiv." -ForegroundColor Yellow
            Write-Host "        Manuell:  .\install-mingw.ps1" -ForegroundColor Yellow
        }
    }
    else {
        $env:PYTENSOR_FLAGS = "mode=FAST_COMPILE,cxx="
        Write-Host "        [WARNUNG] install-mingw.ps1 fehlt -- PyTensor Python-Mode." -ForegroundColor Yellow
    }
}

# -- 4/7 Scientific Stack -----------------------------------------------------
Write-Step 4 "Scientific Stack (LightGBM, Optuna, PyMC, ArviZ, Prefect) ..."
try {
    & $venvPip install --quiet --upgrade lightgbm optuna pymc arviz prefect trafilatura
    Write-Host "        Scientific Stack installiert." -ForegroundColor Green
} catch {
    Write-Host "        [WARNUNG] Einige Scientific-Pakete konnten nicht installiert werden." -ForegroundColor Yellow
}

# -- 5/7 spaCy-Modell ---------------------------------------------------------
$hasModel = $false
try {
    & $venvPy -c "import en_core_web_sm" 2>$null
    $hasModel = ($LASTEXITCODE -eq 0)
} catch { $hasModel = $false }
if (-not $hasModel) {
    Write-Step 5 "spaCy en_core_web_sm wird geladen ..."
    & $venvPy -m spacy download en_core_web_sm --quiet
}
else {
    Write-Step 5 "spaCy-Modell vorhanden" "Green"
}

# -- 6/7 .env -----------------------------------------------------------------
$envFile = Join-Path $backendDir ".env"
if (-not (Test-Path $envFile)) {
    $minEnv = @(
        "USE_MOCK_CRAWLER=true",
        "USE_ARCTIC_SHIFT=false",
        "USE_ROBERTA=false",
        "USE_FACTOR_ENSEMBLE=true",
        "GOAL_MODEL=poisson",
        "DATABASE_URL=sqlite+aiosqlite:///./redditorakel.db",
        "LOG_LEVEL=INFO",
        "USE_NVIDIA_LLM=false",
        "ADMIN_API_KEY="
    )
    $minEnv | Set-Content -Encoding utf8 $envFile
    Write-Step 6 ".env angelegt (Mock-Modus)"
}
else {
    Write-Step 6 ".env vorhanden" "Green"
}

# -- 7/7 Node-Module ---------------------------------------------------------
$nodeModules = Join-Path $frontendDir "node_modules"
if ((Test-Path (Join-Path $frontendDir "package.json")) -and (-not (Test-Path $nodeModules))) {
    Write-Step 7 "npm install ..."
    Push-Location $frontendDir
    if (Test-Path "package-lock.json") {
        npm ci --silent
    } else {
        npm install --silent
    }
    Pop-Location
}
else {
    Write-Step 7 "Frontend-Deps vorhanden / kein Frontend" "Green"
}

Write-Host ""
Write-Host "  [Setup abgeschlossen] Starte ki_runner --mode=$Mode ..." -ForegroundColor White
Write-Host "  ------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

Push-Location $backendDir
try {
    & $venvPy -m scripts.ki_runner "--mode=$Mode"
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "  ------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  ki-run-and-train beendet (Exit $exitCode)." -ForegroundColor Cyan
Write-Host ""
Read-Host "  Druecke ENTER um dieses Fenster zu schliessen"
exit $exitCode
