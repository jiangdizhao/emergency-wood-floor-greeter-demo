param(
    [string]$BaseUrl = 'http://127.0.0.1:8010',
    [string]$OutDir = '.\voice_samples'
)

$ErrorActionPreference = 'Stop'

function Convert-UnicodeEscapesToString {
    param([string]$EscapedText)
    return [System.Text.RegularExpressions.Regex]::Unescape($EscapedText)
}

$voices = @(
    'zm_yunjian',
    'zm_yunxi',
    'zm_yunxia',
    'zm_yunyang'
)

$textEscaped = '\u60a8\u597d\uff0c\u6b22\u8fce\u6765\u5230\u6728\u5730\u677f\u4f53\u9a8c\u533a\u3002\u6211\u662f\u60a8\u7684 AI \u9009\u8d2d\u987e\u95ee\u5c0f\u6728\u3002\u6211\u53ef\u4ee5\u6839\u636e\u60a8\u7684\u623f\u95f4\u3001\u88c5\u4fee\u98ce\u683c\u3001\u9884\u7b97\u548c\u751f\u6d3b\u9700\u6c42\uff0c\u5e2e\u60a8\u9009\u62e9\u5408\u9002\u7684\u5730\u677f\u3002'
$text = Convert-UnicodeEscapesToString $textEscaped

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null

Write-Host 'Checking Kokoro health...' -ForegroundColor Green
Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get | ConvertTo-Json -Depth 10

foreach ($voice in $voices) {
    $outFile = Join-Path $OutDir "$voice.wav"
    $body = @{
        text = $text
        language = 'zh'
        voice = $voice
        speed = 1.0
    } | ConvertTo-Json

    Write-Host "Generating $voice ..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri "$BaseUrl/tts" `
        -Method Post `
        -ContentType 'application/json; charset=utf-8' `
        -Body $body `
        -OutFile $outFile
}

Write-Host ''
Write-Host "Saved four Mandarin male voice samples to $OutDir" -ForegroundColor Green
Get-ChildItem -Path $OutDir -Filter '*.wav' | Select-Object Name, Length, LastWriteTime
