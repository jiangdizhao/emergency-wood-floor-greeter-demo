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
$SalesKnowledge = Join-Path $BackendRoot 'app\services\sales_knowledge_service.py'

Write-Host 'Checking proactive sales runtime, customer greeting and natural Kokoro settings...' -ForegroundColor Green
Write-Host "Repository: $RepoRoot" -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js is required for the proactive-sales JavaScript syntax check.'
}

& node --check $ProactiveScript
if ($LASTEXITCODE -ne 0) {
    throw "proactive-sales.js syntax check failed with exit code $LASTEXITCODE."
}

& $PythonExe -m py_compile $TtsServer $SalesKnowledge
if ($LASTEXITCODE -ne 0) {
    throw "Python syntax check failed with exit code $LASTEXITCODE."
}

$proactive = Get-Content -Raw -Encoding UTF8 $ProactiveScript
$index = Get-Content -Raw -Encoding UTF8 $IndexHtml
$tts = Get-Content -Raw -Encoding UTF8 $TtsServer
$ttsStartText = Get-Content -Raw -Encoding UTF8 $TtsStart
$salesKnowledgeText = Get-Content -Raw -Encoding UTF8 $SalesKnowledge

$requiredProactivePatterns = @(
    'IDLE_DELAYS_MS = [8000, 10000, 10000, 14000]',
    'QUESTION_RESPONSE_DELAY_MS = 45000',
    'QUESTION_BUSY_RETRY_MS = 1800',
    'QUESTION_BUSY_MAX_WAIT_MS = 10000',
    'waitingForCustomerAnswer',
    'questionWaitAtSchedule',
    'questionBusyDeadline',
    'assistantAskedQuestion',
    'payload.greeting',
    'suspendCadence',
    "url.includes('/api/chat') || url.includes('/api/identity/session/')",
    'last_assistant_question',
    'needs_clarification',
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

$requiredBootstrapPatterns = @(
    "localStorage.removeItem('woodfloor_proactive_sales_enabled')",
    "window.__WOODFLOOR_PROACTIVE_BOOTSTRAP_VERSION__ = '2026-07-14.2'",
    '/proactive-sales.js?v=20260714-2'
)
foreach ($pattern in $requiredBootstrapPatterns) {
    if (-not $index.Contains($pattern)) {
        throw "Missing proactive recovery bootstrap: $pattern"
    }
}

if (-not $index.Contains('proactive-sales-dock')) {
    throw 'ui/index.html does not contain proactive sales dock styling.'
}

$requiredGreetingPatterns = @(
    '我可以为您介绍不同材质的特点',
    '结合实际家庭使用场景给出主推款和备选款',
    '您这次选地板最关注耐磨、防水、脚感、好清洁、预算还是环保？'
)
foreach ($pattern in $requiredGreetingPatterns) {
    if (-not $salesKnowledgeText.Contains($pattern)) {
        throw "Missing customer-facing greeting contract: $pattern"
    }
}

$forbiddenGreetingPatterns = @(
    '我不会让您一开始就回答一长串问题',
    '拿两款有代表性的产品把差别讲清楚'
)
foreach ($pattern in $forbiddenGreetingPatterns) {
    if ($salesKnowledgeText.Contains($pattern)) {
        throw "Internal dialogue-design principle leaked into customer greeting: $pattern"
    }
}

$requiredTtsPatterns = @(
    'version="0.7.1"',
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

if (-not $ttsStartText.Contains('KOKORO_ZH_PROSODY_MODE')) {
    throw 'Kokoro startup script does not configure Mandarin prosody mode.'
}
if (-not $ttsStartText.Contains("KOKORO_CLAUSE_PAUSE_MS = '0'")) {
    throw 'Kokoro startup script must keep synthetic clause pauses disabled.'
}
if (-not $ttsStartText.Contains("KOKORO_SENTENCE_PAUSE_MS = '0'")) {
    throw 'Kokoro startup script must keep synthetic sentence pauses disabled.'
}

Write-Host 'Proactive sales, customer greeting and natural TTS static check passed.' -ForegroundColor Green
Write-Host 'Normal idle narration cadence: 8s, 10s, 10s, 14s; then stop until customer activity.'
Write-Host 'Assistant-question response window: 45s from both chat answers and the opening greeting.'
Write-Host 'After the 45s grace period, busy UI state is retried every 1.8s and cannot suppress narration indefinitely.'
Write-Host 'A stale browser pause flag is cleared before proactive-sales.js loads, and the script URL is cache-busted.'
Write-Host 'Customer greeting describes store capabilities and products, not internal dialogue-design rules.'
Write-Host 'Product, collection, promotion and optional contact stories: enabled.'
Write-Host 'Listening, typing, processing and speaking interruption guards: enabled.'
Write-Host 'Mandarin soft prosody: enabled.'
Write-Host 'Synthetic punctuation silence: disabled.'
Write-Host 'Per-voice pacing and natural edge padding: enabled.'
