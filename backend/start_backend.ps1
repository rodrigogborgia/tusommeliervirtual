$ErrorActionPreference = "Stop"

# Ejecutar desde la raíz del repo (recomendado):
#   .\backend\start_backend.ps1

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Repo root: $repoRoot"
Set-Location $repoRoot

if (-Not (Test-Path ".\backend\venv")) {
  Write-Host "No se encontró .\backend\venv. Creando venv..."
  python -m venv .\backend\venv
}

Write-Host "Activando venv..."
& .\backend\venv\Scripts\Activate.ps1

Write-Host "Instalando dependencias..."
pip install -r .\backend\requirements.txt

Write-Host "Levantando backend en http://localhost:8001 ..."
# Forzar backend WS para evitar que el handshake caiga como HTTP (404)
python -m uvicorn backend.server:app --host 0.0.0.0 --port 8001 --reload --log-level debug --ws websockets


