param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $BackendRoot '..')).Path
$RuntimeSource = Join-Path $RepoRoot 'ui\src\realtimeAgentRuntime.ts'
$LongAudioPatchSource = Join-Path $RepoRoot 'ui\src\realtimeLongAudioTimeoutPatch.ts'
$RecognitionSource = Join-Path $RepoRoot 'ui\src\realtimeSpeechRecognitionV2.ts'
$RouteGuardSource = Join-Path $RepoRoot 'ui\src\routedInteractionGuard.ts'
$VoiceManagerSource = Join-Path $RepoRoot 'ui\src\voiceOutputManager.ts'
$MainSource = Join-Path $RepoRoot 'ui\src\main.tsx'
$IndexSource = Join-Path $RepoRoot 'ui\index.html'
$RouterSource = Join-Path $BackendRoot 'app\services\turn_router.py'
$InteractionApiSource = Join-Path $BackendRoot 'app\interaction_api.py'
$RemovedCircuitSource = Join-Path $RepoRoot 'ui\src\realtimeOutputCircuitBreaker.ts'
$RemovedAckSource = Join-Path $RepoRoot 'ui\src\realtimePlaybackAck.ts'
$RemovedProactivePatch = Join-Path $RepoRoot 'ui\public\proactive-tts-auto-patch.js'
$RemovedProactiveRuntime = Join-Path $RepoRoot 'ui\public\proactive-sales.js'

Write-Host "Checking strict office voice-output contracts..." -ForegroundColor Cyan

$status = Invoke-RestMethod -Uri "$BaseUrl/api/realtime/status" -Method Get
if (-not $status.ok) { throw "Realtime status endpoint did not return ok=true." }
if ($status.transport -ne "webrtc") { throw "Expected transport=webrtc." }
if ($status.turn_mode -ne "push_to_talk") { throw "Expected turn_mode=push_to_talk." }

$runtime = Get-Content -Raw -Encoding UTF8 $RuntimeSource
$longAudioPatch = Get-Content -Raw -Encoding UTF8 $LongAudioPatchSource
$recognition = Get-Content -Raw -Encoding UTF8 $RecognitionSource
$routeGuard = Get-Content -Raw -Encoding UTF8 $RouteGuardSource
$voiceManager = Get-Content -Raw -Encoding UTF8 $VoiceManagerSource
$main = Get-Content -Raw -Encoding UTF8 $MainSource
$index = Get-Content -Raw -Encoding UTF8 $IndexSource
$router = Get-Content -Raw -Encoding UTF8 $RouterSource
$interactionApi = Get-Content -Raw -Encoding UTF8 $InteractionApiSource

$runtimePatterns = @(
    "createMediaStreamDestination",
    "pc.addTrack(this.silentTrack, this.silentStream)",
    "this.sender.replaceTrack(track)",
    "input_audio_buffer.commit",
    "input_audio_buffer.committed",
    "restoreSilentTrack",
    "response.output_audio_transcript.delta",
    "output_audio_buffer.started",
    "output_audio_buffer.stopped"
)
foreach ($pattern in $runtimePatterns) {
    if (-not $runtime.Contains($pattern)) {
        throw "Missing persistent Realtime runtime contract: $pattern"
    }
}

$longAudioPatterns = @(
    "AUDIO_START_TIMEOUT_MS = 15_000",
    "MIN_AUDIO_COMPLETION_TIMEOUT_MS = 90_000",
    "MAX_AUDIO_COMPLETION_TIMEOUT_MS = 360_000",
    "estimateAudioCompletionTimeoutMs",
    "audioCompletionTimeoutMs",
    "output_audio_buffer.started",
    "GPT Realtime audio did not start within 15 seconds.",
    "createResponseWithAudioAwareTimeout",
    "handleServerEventWithAudioAwareTimeout"
)
foreach ($pattern in $longAudioPatterns) {
    if (-not $longAudioPatch.Contains($pattern)) {
        throw "Missing long Realtime audio timeout contract: $pattern"
    }
}

$recognitionPatterns = @(
    "getRealtimeAgentRuntime",
    ".stopOutput()",
    ".then(() => detachIdleInputTrack(agent))",
    ".then(() => agent.beginCapture())",
    ".endCapture()",
    "sender.replaceTrack(null)"
)
foreach ($pattern in $recognitionPatterns) {
    if (-not $recognition.Contains($pattern)) {
        throw "Missing Realtime recognition contract: $pattern"
    }
}

$routeGuardPatterns = @(
    '/api/interaction/${path}',
    "fetchRoute('classify', body)",
    "payload = await fetchRoute('route', body)",
    "getVoiceOutputMode() === 'realtime'",
    "respondDirectText",
    "realtime_direct_text",
    "audio_already_played",
    "woodfloor:voice-output-played",
    "woodfloor:voice-output-stop",
    "No spoken progress cue"
)
foreach ($pattern in $routeGuardPatterns) {
    if (-not $routeGuard.Contains($pattern)) {
        throw "Missing strict routed-interaction contract: $pattern"
    }
}

$forbiddenRouteGuardPatterns = @(
    "progressCue()",
    "skipNextTtsText",
    "kokoroSmalltalkFallback",
    "silentWavResponse"
)
foreach ($pattern in $forbiddenRouteGuardPatterns) {
    if ($routeGuard.Contains($pattern)) {
        throw "Obsolete multi-owner voice behavior remains in route guard: $pattern"
    }
}

$voiceManagerPatterns = @(
    "export type VoiceOutputMode = 'realtime' | 'kokoro' | 'openai'",
    "provider = mode === KOKORO_MODE ? 'local' : 'openai'",
    "X-Woodfloor-Strict-Voice-Mode",
    "DUPLICATE_SUPPRESSION_MS",
    "installSingleMediaOwner",
    "disableBrowserSpeechFallback",
    "Automatic voice fallback is disabled",
    "window.dispatchEvent(new CustomEvent('woodfloor:voice-output-changed'",
    "return acknowledgementResponse('gpt-realtime', message)",
    "return acknowledgementResponse(mode === KOKORO_MODE ? 'local-kokoro' : 'openai', message)"
)
foreach ($pattern in $voiceManagerPatterns) {
    if (-not $voiceManager.Contains($pattern)) {
        throw "Missing strict single-owner voice contract: $pattern"
    }
}

if (-not $main.Contains("import './realtimeLongAudioTimeoutPatch'")) {
    throw "The long Realtime audio timeout patch is not loaded."
}
if ($main.IndexOf("import './realtimeLongAudioTimeoutPatch'") -lt $main.IndexOf("import './speechRecognitionDomainPatch'")) {
    throw "The long audio timeout patch must load after the Realtime runtime is created."
}
if (-not $main.Contains("import './voiceOutputManager'")) {
    throw "The strict voice output manager is not loaded."
}
if ($main.Contains("realtimeOutputCircuitBreaker") -or $main.Contains("realtimePlaybackAck")) {
    throw "Obsolete automatic fallback modules are still imported."
}

$forbiddenIndexPatterns = @(
    "proactive-sales",
    "proactive-tts-auto-patch",
    "woodfloor_proactive_sales_enabled",
    "__WOODFLOOR_PROACTIVE_BOOTSTRAP_VERSION__"
)
foreach ($pattern in $forbiddenIndexPatterns) {
    if ($index.Contains($pattern)) {
        throw "Office frontend still contains proactive narration UI/runtime: $pattern"
    }
}

$removedFiles = @(
    $RemovedCircuitSource,
    $RemovedAckSource,
    $RemovedProactivePatch,
    $RemovedProactiveRuntime
)
foreach ($path in $removedFiles) {
    if (Test-Path $path) {
        throw "Removed office-only voice/proactive file still exists: $path"
    }
}

$routerPatterns = @(
    '"deterministic_direct"',
    '"realtime_direct"',
    '"terra"',
    '"repeat_last"',
    '"stop_speaking"',
    'unknown turns default to the guarded Terra pipeline'
)
foreach ($pattern in $routerPatterns) {
    if (-not $router.Contains($pattern)) {
        throw "Missing authoritative route contract: $pattern"
    }
}

if (-not $interactionApi.Contains('@router.post("/api/interaction/classify")')) {
    throw "The fast interaction-classification endpoint is not registered."
}
if (-not $interactionApi.Contains('@router.post("/api/interaction/route")')) {
    throw "The routed interaction-execution endpoint is not registered."
}

if ($recognition.Contains("new RTCPeerConnection")) {
    throw "SpeechRecognition wrapper still constructs a per-turn WebRTC connection."
}

Write-Host "Strict office voice-output contracts passed." -ForegroundColor Green
Write-Host "Model configured: $($status.model)"
Write-Host "Proactive narration runtime and its frontend dock are absent from the office branch."
Write-Host "The user selects exactly one output owner: GPT Realtime 2, Kokoro, or OpenAI TTS."
Write-Host "Provider errors remain visible and do not trigger another voice or browser TTS."
Write-Host "Long Realtime audio gets a 15-second start timeout and a 90-360 second completion window."
Write-Host "Only one HTML media element may play at a time; push-to-talk still owns microphone interruption."
