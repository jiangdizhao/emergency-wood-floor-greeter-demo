param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $BackendRoot '..')).Path
$RuntimeSource = Join-Path $RepoRoot 'ui\src\realtimeAgentRuntime.ts'
$RecognitionSource = Join-Path $RepoRoot 'ui\src\realtimeSpeechRecognitionV2.ts'
$RouterSource = Join-Path $BackendRoot 'app\services\turn_router.py'
$InteractionApiSource = Join-Path $BackendRoot 'app\interaction_api.py'

Write-Host "Checking persistent GPT Realtime agent contracts..." -ForegroundColor Cyan

$status = Invoke-RestMethod -Uri "$BaseUrl/api/realtime/status" -Method Get
if (-not $status.ok) { throw "Realtime status endpoint did not return ok=true." }
if ($status.transport -ne "webrtc") { throw "Expected transport=webrtc." }
if ($status.turn_mode -ne "push_to_talk") { throw "Expected push_to_talk mode." }

$runtime = Get-Content -Raw -Encoding UTF8 $RuntimeSource
$recognition = Get-Content -Raw -Encoding UTF8 $RecognitionSource
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
    "GPT Realtime（默认）",
    "Kokoro 本地语音",
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
    ".then(() => agent.beginCapture())",
    ".endCapture()",
    "localStorage.setItem(PROVIDER_STORAGE_KEY, REALTIME_PROVIDER)"
)
foreach ($pattern in $recognitionPatterns) {
    if (-not $recognition.Contains($pattern)) {
        throw "Missing Realtime recognition contract: $pattern"
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

if (-not $interactionApi.Contains('@router.post("/api/interaction/route")')) {
    throw "The routed interaction endpoint is not registered."
}

$legacyPerTurnPattern = "new RTCPeerConnection"
if ($recognition.Contains($legacyPerTurnPattern)) {
    throw "SpeechRecognition wrapper still constructs a per-turn WebRTC connection."
}

Write-Host "Persistent GPT Realtime frontend and routing contracts passed." -ForegroundColor Green
Write-Host "Model configured: $($status.model)"
Write-Host "The physical microphone is push-to-talk only; a silent negotiated track keeps the session reusable."
Write-Host "GPT Realtime is the default output; Kokoro remains user-selectable and is used after Realtime output failure."
