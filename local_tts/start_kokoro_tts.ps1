param(
    [int]$Port = 8010,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

Write-Host "Starting local Kokoro TTS server..." -ForegroundColor Green
Write-Host "Host: $HostAddress" -ForegroundColor Cyan
Write-Host "Port: $Port" -ForegroundColor Cyan
Write-Host "Health: http://${HostAddress}:${Port}/health" -ForegroundColor Cyan
Write-Host ""

uvicorn kokoro_tts_server:app --host $HostAddress --port $Port
