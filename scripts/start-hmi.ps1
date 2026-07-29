# Arranque HMI R-Bot Industrial en Windows (modo mock)
# Requiere: Python 3.10+
# Uso (PowerShell):
#   cd path\to\rbot-industrial
#   .\scripts\start-hmi.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ApiDir = Join-Path $Root "apps\api"

Set-Location $ApiDir

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Creado apps/api/.env (mock)"
}

if (-not (Test-Path ".venv")) {
  Write-Host "Creando venv..."
  py -3 -m venv .venv
}

$Py = Join-Path $ApiDir ".venv\Scripts\python.exe"
& $Py -m pip install -q -r requirements.txt

Write-Host "API + HMI en http://127.0.0.1:8000"
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
