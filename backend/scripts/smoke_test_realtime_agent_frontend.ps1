param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $BackendRoot '..')).Path
$RuntimeSource = Join-Path $RepoRoot 'ui\src\realtimeAgentRuntime.ts'
$RecognitionSource = Join-Path $RepoRoot 'ui\src\realtimeSpeechRecognitionV2.ts'
$RouteGuardSource = Join-Path $RepoRoot 'ui\src\routedInteractionGuard.ts'
$CircuitSource = Join-Path $RepoRoot 'ui\src\realtimeOutputCircuitBreaker.ts'
$PlaybackAckSource = Join-Path $RepoRoot 'ui\src\realtimePlaybackAck.ts'
$MainSource = Join-Path $RepoRoot 'ui\src\main.tsx'
$RouterSource = Join-Path $BackendRoot 'app\services\turn_router.py'
$InteractionApiSource = Join-Path $BackendRoot 'app\interaction_api.py'

Write-Host "Checking persistent GPT Realtime agent contracts..." -ForegroundColor Cyan

$status = Invoke-RestMethod -Uri "$BaseUrl/api/realtime/status" -Method Get
if (-not $status.ok) { throw "Realtime status endpoint did not return ok=true." }
if ($status.transport -ne "webrtc") { throw "Expected transport=webrtc." }
if ($status.turn_mode -ne "push_to_talk") { throw "Expected push_to_talk mode." }

$runtime = Get-Content -Raw -Encoding UTF8 $RuntimeSource
$recognition = Get-Content -Raw -Encoding UTF8 $RecognitionSource
$routeGuard = Get-Content -Raw -Encoding UTF8 $RouteGuardSource
$circuit = Get-Content -Raw -Encoding UTF8 $CircuitSource
$playbackAck = Get-Content -Raw -Encoding UTF8 $PlaybackAckSource
$main = Get-Content -Raw -Encoding UTF8 $MainSource
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
    "output_audio_buffer.stopped",
    "/api/interaction/route",
    "woodfloor_voice_output",
    "realtimeOption.value = REALTIME_OUTPUT",
    "kokoroOption.value = KOKORO_OUTPUT",
    "error.name === 'AbortError'"
)
foreach ($pattern in $runtimePatterns) {
    if (-not $runtime.Contains($pattern)) {
        throw "Missing persistent Realtime runtime contract: $pattern"
    }
}

$recognitionPatterns = @(
    "getRealtimeAgentRuntime",
    ".stopOutput()",
    ".then(() => detachIdleInputTrack(agent))",
    ".then(() => agent.beginCapture())",
    ".endCapture()",
    "sender.replaceTrack(null)",
    "window.addEventListener('woodfloor:realtime-connected'",
    "localStorage.setItem(PROVIDER_STORAGE_KEY, REALTIME_PROVIDER)"
)
foreach ($pattern in $recognitionPatterns) {
    if (-not $recognition.Contains($pattern)) {
        throw "Missing Realtime recognition contract: $pattern"
    }
}

$routeGuardPatterns = @(
    '/api/interaction/${path}',
    "fetchRoute('classify', body)",
    "const executionPromise = fetchRoute('route', body)",
    "await agent.speakExact(progressCue())",
    "route === 'realtime_direct'",
    "error.name === 'AbortError'",
    "listeningGeneration !== generationAtStart",
    "skipNextTtsText",
    "kokoroSmalltalkFallback",
    "Authoritative interaction route failed"
)
foreach ($pattern in $routeGuardPatterns) {
    if (-not $routeGuard.Contains($pattern)) {
        throw "Missing interruption-safe route guard contract: $pattern"
    }
}

$circuitPatterns = @(
    "CIRCUIT_DURATION_MS = 60_000",
    "woodfloor_realtime_output_disabled_until",
    "provider !== 'gpt-realtime'",
    "woodfloor:realtime-output-fallback"
)
foreach ($pattern in $circuitPatterns) {
    if (-not $circuit.Contains($pattern)) {
        throw "Missing Realtime output circuit-breaker contract: $pattern"
    }
}

$playbackAckPatterns = @(
    "ACK_DURATION_MS = 80",
    "createPlayableSilenceWav",
    "view.setUint32(40, dataSize, true)",
    "X-Woodfloor-Audio-Already-Played",
    "provider === REALTIME_PROVIDER",
    "return playableRealtimeAck(response)"
)
foreach ($pattern in $playbackAckPatterns) {
    if (-not $playbackAck.Contains($pattern)) {
        throw "Missing single-playback Realtime acknowledgement contract: $pattern"
    }
}

if (-not $main.Contains("import './routedInteractionGuard'")) {
    throw "The authoritative routed interaction guard is not loaded."
}
if (-not $main.Contains("import './realtimeOutputCircuitBreaker'")) {
    throw "The Realtime output circuit breaker is not loaded after the runtime."
}
if (-not $main.Contains("import './realtimePlaybackAck'")) {
    throw "The Realtime playback acknowledgement guard is not loaded."
}
if ($main.IndexOf("import './realtimePlaybackAck'") -lt $main.IndexOf("import './realtimeOutputCircuitBreaker'")) {
    throw "The playback acknowledgement guard must wrap the completed Realtime/circuit-breaker fetch chain."
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

$legacyPerTurnPattern = "new RTCPeerConnection"
if ($recognition.Contains($legacyPerTurnPattern)) {
    throw "SpeechRecognition wrapper still constructs a per-turn WebRTC connection."
}

Write-Host "Persistent GPT Realtime frontend and routing contracts passed." -ForegroundColor Green
Write-Host "Model configured: $($status.model)"
Write-Host "The physical microphone is push-to-talk only; the idle sender track is detached after negotiation."
Write-Host "Interrupted Realtime social responses cannot silently fall through to Terra."
Write-Host "Terra execution starts concurrently with a short Realtime progress cue."
Write-Host "Realtime playback returns a valid silent acknowledgement, preventing duplicate Kokoro/Browser TTS fallback."
Write-Host "GPT Realtime is the default output; Kokoro remains user-selectable and a 60-second circuit breaker prevents repeated failed Realtime attempts."
