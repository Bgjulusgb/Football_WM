# install-mingw.ps1 — RedditOrakel v3.6
# Installiert MSYS2 + mingw-w64-ucrt-x86_64-gcc (g++) damit PyTensor (PyMC) im
# schnellen C-Backend laeuft. Idempotent: ueberspringt was schon da ist.
#
# Aufruf:
#   .\install-mingw.ps1
# oder aus ki-run-and-train.bat / ki-run-and-train.ps1.

[CmdletBinding()]
param(
    [switch]$Quiet,
    [switch]$NoPathUpdate
)

$ErrorActionPreference = "Continue"

function Write-Info($msg)    { Write-Host "  [install-mingw] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)      { Write-Host "  [install-mingw] $msg" -ForegroundColor Green }
function Write-Warn($msg)    { Write-Host "  [install-mingw] $msg" -ForegroundColor Yellow }
function Write-Err($msg)     { Write-Host "  [install-mingw] $msg" -ForegroundColor Red }

$gppPath  = "C:\msys64\ucrt64\bin\g++.exe"
$ucrtBin  = "C:\msys64\ucrt64\bin"
$bashPath = "C:\msys64\usr\bin\bash.exe"

# 1) Schon im PATH?
$existing = Get-Command g++ -ErrorAction SilentlyContinue
if ($existing) {
    Write-Ok "g++ bereits im PATH: $($existing.Source)"
    exit 0
}

# 2) Schon installiert (nur PATH fehlt)?
if (Test-Path $gppPath) {
    Write-Ok "g++ gefunden unter $gppPath"
    if (-not $NoPathUpdate) {
        $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
        if ($userPath -notlike "*$ucrtBin*") {
            [Environment]::SetEnvironmentVariable("PATH", "$ucrtBin;$userPath", "User")
            Write-Ok "User-PATH erweitert um $ucrtBin (neues Terminal noetig)."
        } else {
            Write-Info "User-PATH enthaelt bereits $ucrtBin."
        }
        $env:PATH = "$ucrtBin;$env:PATH"
    }
    exit 0
}

# 3) MSYS2 vorhanden, gcc fehlt? -> pacman
if (Test-Path $bashPath) {
    Write-Info "MSYS2 vorhanden, installiere mingw-w64-ucrt-x86_64-gcc via pacman ..."
    try {
        & $bashPath -lc "pacman -Sy --noconfirm mingw-w64-ucrt-x86_64-gcc" | Out-Null
    } catch {
        Write-Warn "pacman-Aufruf fehlgeschlagen: $($_.Exception.Message)"
    }
    if (Test-Path $gppPath) {
        Write-Ok "g++ erfolgreich installiert."
        if (-not $NoPathUpdate) {
            $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
            if ($userPath -notlike "*$ucrtBin*") {
                [Environment]::SetEnvironmentVariable("PATH", "$ucrtBin;$userPath", "User")
                Write-Ok "User-PATH erweitert um $ucrtBin."
            }
            $env:PATH = "$ucrtBin;$env:PATH"
        }
        exit 0
    }
    Write-Warn "pacman lief, g++ aber nicht da. Fallback auf winget."
}

# 4) winget verfuegbar?
$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
    Write-Err "winget nicht verfuegbar. Manuelle Installation noetig:"
    Write-Err "  1) Download MSYS2: https://www.msys2.org/"
    Write-Err "  2) Installer ausfuehren (Default-Pfad C:\msys64)"
    Write-Err "  3) MSYS2 oeffnen, 'pacman -S mingw-w64-ucrt-x86_64-gcc'"
    Write-Err "  4) Dieses Script erneut ausfuehren um den PATH zu setzen."
    exit 1
}

Write-Info "Installiere MSYS2 via winget ..."
try {
    if ($Quiet) {
        & winget install -e --id MSYS2.MSYS2 --silent --accept-source-agreements --accept-package-agreements | Out-Null
    } else {
        & winget install -e --id MSYS2.MSYS2 --silent --accept-source-agreements --accept-package-agreements
    }
} catch {
    Write-Err "winget install fehlgeschlagen: $($_.Exception.Message)"
    exit 1
}

if (-not (Test-Path $bashPath)) {
    Write-Err "MSYS2 ist nach winget nicht in C:\msys64 zu finden."
    Write-Err "Bitte manuell installieren: https://www.msys2.org/"
    exit 1
}

Write-Info "Installiere mingw-w64-ucrt-x86_64-gcc via pacman ..."
try {
    & $bashPath -lc "pacman -Sy --noconfirm mingw-w64-ucrt-x86_64-gcc" | Out-Null
} catch {
    Write-Err "pacman-Installation fehlgeschlagen: $($_.Exception.Message)"
    exit 1
}

if (-not (Test-Path $gppPath)) {
    Write-Err "g++ nach pacman-Lauf nicht gefunden ($gppPath)."
    Write-Err "Pruefe MSYS2 manuell: pacman -S mingw-w64-ucrt-x86_64-gcc"
    exit 1
}

Write-Ok "g++ erfolgreich installiert."

if (-not $NoPathUpdate) {
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -notlike "*$ucrtBin*") {
        [Environment]::SetEnvironmentVariable("PATH", "$ucrtBin;$userPath", "User")
        Write-Ok "User-PATH erweitert um $ucrtBin (neues Terminal noetig)."
    } else {
        Write-Info "User-PATH enthaelt bereits $ucrtBin."
    }
    $env:PATH = "$ucrtBin;$env:PATH"
}

Write-Ok "Fertig. PyTensor laeuft jetzt im schnellen C-Backend."
exit 0
