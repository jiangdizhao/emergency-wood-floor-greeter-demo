param(
    [string]$PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'
$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $BackendRoot '..')).Path
$ProactiveScript = Join-Path $RepoRoot 'ui\public\proactive-sales.js'
$IndexHtml = Join-Path $RepoRoot 'ui\index.html'
$TtsServer = Join-Path $RepoRoot 'local_tts\kokoro_tts_server.py'
$TtsStart = Join-Path $RepoRoot 'local_tts\start_kokoro_tts.ps1'

Write-Host 'Checking proactive sales runtime and natural Kokoro settings...' -ForegroundColor Green
Write-Host "Repository: $RepoRoot" -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js is required for the proactive-sales JavaScript syntax check.'
}

& node --check $ProactiveScript
if ($LASTEXITCODE -ne 0) {
    throw "proactive-sales.js syntax check failed with exit code $LASTEXITCODE."
}

& $PythonExe -m py_compile $TtsServer
if ($LASTEXITCODE -ne 0) {
    throw "kokoro_tts_server.py syntax check failed with exit code $LASTEXITCODE."
}

$proactive = Get-Content -Raw -Encoding UTF8 $ProactiveScript
$index = Get-Content -Raw -Encoding UTF8 $IndexHtml
$tts = Get-Content -Raw -Encoding UTF8 $TtsServer
$ttsStartText = Get-Content -Raw -Encoding UTF8 $TtsStart

$requiredProactivePatterns = @(
    'IDLE_DELAYS_MS = [8000, 10000, 10000, 14000]',
    'MAX_PROACTIVE_STEPS',
    'contact_prompt_eligible',
    'Get My Plan and Follow-Up',
    '获取方案与后续联系',
    'proactive_sales_enabled',
    'status-pulse.listening',
    'currentAudio'
)
foreach ($pattern in $requiredProactivePatterns) {
    if (-not $proactive.Contains($pattern)) {
        throw "Missing proactive sales contract: $pattern"
    }
}

if (-not $index.Contains('/proactive-sales.js')) {
    throw 'ui/index.html does not load proactive-sales.js.'
}
if (-not $index.Contains('proactive-sales-dock')) {
    throw 'ui/index.html does not contain proactive sales dock styling.'
}

$requiredTtsPatterns = @(
    'version="0.7.0"',
    'KOKORO_ZH_PROSODY_MODE',
    'ZH_VOICE_SPEEDS',
    '_soft_mandarin_prosody',
    'SILENCE_THRESHOLD_DB',
    'SILENCE_PAD_MS',
    'CHUNK_CROSSFADE_MS'
)
foreach ($pattern in $requiredTtsPatterns) {
    if (-not $tts.Contains($pattern)) {
        throw "Missing natural TTS contract: $pattern"
    }
}

if (-not $ttsStartText.Contains("KOKORO_ZH_PROSODY_MODE")) {
    throw 'Kokoro startup script does not configure Mandarin prosody mode.'
}
if (-not $ttsStartText.Contains("KOKORO_CLAUSE_PAUSE_MS = '0'")) {
    throw 'Kokoro startup script must keep synthetic clause pauses disabled.'
}
if (-not $ttsStartText.Contains("KOKORO_SENTENCE_PAUSE_MS = '0'")) {
    throw 'Kokoro startup script must keep synthetic sentence pauses disabled.'
}

Write-Host 'Proactive sales and natural TTS static check passed.' -ForegroundColor Green
Write-Host 'Idle narration cadence: 8s, 10s, 10s, 14s; then stop until customer activity.'
Write-Host 'Product, collection, promotion and optional contact stories: enabled.'
Write-Host 'Listening, typing, processing and speaking interruption guards: enabled.'
Write-Host 'Mandarin soft prosody: enabled.'
Write-Host 'Synthetic punctuation silence: disabled.'
Write-Host 'Per-voice pacing and natural edge padding: enabled.'
