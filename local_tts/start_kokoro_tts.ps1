param(
    [int]$Port = 8010,
    [string]$HostAddress = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'

Write-Host 'Starting local Kokoro TTS server...' -ForegroundColor Green
Write-Host "Host: $HostAddress" -ForegroundColor Cyan
Write-Host "Port: $Port" -ForegroundColor Cyan
Write-Host "Health: http://${HostAddress}:${Port}/health" -ForegroundColor Cyan
Write-Host ''

Write-Host 'Python executable:' -ForegroundColor Yellow
python -c "import sys; print(sys.executable)"
Write-Host 'Uvicorn module:' -ForegroundColor Yellow
python -c "import uvicorn, sys; print(uvicorn.__file__)"
Write-Host ''

python -m uvicorn kokoro_tts_server:app --host $HostAddress --port $Port
