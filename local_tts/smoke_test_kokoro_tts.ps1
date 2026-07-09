param(
    [string]$BaseUrl = "http://127.0.0.1:8010",
    [string]$OutFile = ".\kokoro_local_test.wav",
    [string]$Language = "en"
)

$ErrorActionPreference = "Stop"

Write-Host "[1] Checking local Kokoro TTS health" -ForegroundColor Green
Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get | ConvertTo-Json -Depth 10

Write-Host ""
Write-Host "[2] Requesting local Kokoro TTS wav" -ForegroundColor Green

if ($Language -eq "zh") {
    $text = "你好，欢迎来到木地板体验区。我可以帮你比较防水、耐磨、地暖适配和日常维护。"
} else {
    $text = "Hello, welcome to the wood flooring experience area. I can help you choose a floor that is easy to clean and suitable for pets."
}

$body = @{
    text = $text
    language = $Language
    speed = 1.0
} | ConvertTo-Json

Invoke-WebRequest -Uri "$BaseUrl/tts" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body $body `
    -OutFile $OutFile

Write-Host "Saved local Kokoro audio to $OutFile" -ForegroundColor Cyan
