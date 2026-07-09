param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$OutFile = ".\openai_tts_test.mp3"
)

$ErrorActionPreference = "Stop"

Write-Host "[1] Checking TTS status" -ForegroundColor Green
$status = Invoke-RestMethod -Uri "$BaseUrl/api/tts/status" -Method Get
$status | ConvertTo-Json -Depth 10

if (-not $status.openai_tts_configured) {
    Write-Host ""
    Write-Host "OPENAI_API_KEY is not set for the backend process." -ForegroundColor Yellow
    Write-Host "Set it before starting uvicorn, for example:" -ForegroundColor Yellow
    Write-Host '$env:OPENAI_API_KEY="sk-..."' -ForegroundColor Yellow
    Write-Host "uvicorn app.main:app --reload --port 8000" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "[2] Requesting OpenAI TTS mp3" -ForegroundColor Green
$body = @{
    text = "Hello, welcome to the wood flooring experience area. I can help you choose a floor that is easy to clean and suitable for pets."
    language = "en"
    provider = "openai"
} | ConvertTo-Json

Invoke-WebRequest -Uri "$BaseUrl/api/tts" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body $body `
    -OutFile $OutFile

Write-Host "Saved test audio to $OutFile" -ForegroundColor Cyan
