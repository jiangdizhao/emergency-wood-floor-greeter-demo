param(
    [string]$BaseUrl = 'http://127.0.0.1:8010',
    [string]$OutFile = '.\kokoro_local_test.wav',
    [ValidateSet('en', 'zh')]
    [string]$Language = 'en',
    [string]$Voice = ''
)

$ErrorActionPreference = 'Stop'

function Convert-UnicodeEscapesToString {
    param([string]$EscapedText)
    return [System.Text.RegularExpressions.Regex]::Unescape($EscapedText)
}

Write-Host '[1] Checking local Kokoro TTS health' -ForegroundColor Green
Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get | ConvertTo-Json -Depth 10

Write-Host ''
Write-Host '[2] Requesting local Kokoro TTS wav' -ForegroundColor Green

$textEn = 'Hello, welcome to the wood flooring experience area. I can help you choose a floor that is easy to clean and suitable for pets.'
$textZhEscaped = '\u4f60\u597d\uff0c\u6b22\u8fce\u6765\u5230\u6728\u5730\u677f\u4f53\u9a8c\u533a\u3002\u6211\u662f\u60a8\u7684 AI \u9009\u8d2d\u987e\u95ee\u5c0f\u6728\uff0c\u53ef\u4ee5\u5e2e\u60a8\u6bd4\u8f83\u9632\u6c34\u3001\u8010\u78e8\u3001\u5730\u6696\u9002\u914d\u548c\u65e5\u5e38\u7ef4\u62a4\u3002'

if ($Language -eq 'zh') {
    $text = Convert-UnicodeEscapesToString $textZhEscaped
} else {
    $text = $textEn
}

$payload = @{
    text = $text
    language = $Language
    speed = 1.0
}

if ($Voice) {
    $payload.voice = $Voice
}

$body = $payload | ConvertTo-Json

Invoke-WebRequest -Uri "$BaseUrl/tts" `
    -Method Post `
    -ContentType 'application/json; charset=utf-8' `
    -Body $body `
    -OutFile $OutFile

$voiceLabel = if ($Voice) { $Voice } else { 'server default' }
Write-Host "Saved local Kokoro audio to $OutFile (voice: $voiceLabel)" -ForegroundColor Cyan
