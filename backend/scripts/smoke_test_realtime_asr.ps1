param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $BackendRoot '..')).Path
$RuntimeSource = Join-Path $RepoRoot 'ui\src\realtimeAgentRuntime.ts'
$RecognitionSource = Join-Path $RepoRoot 'ui\src\realtimeSpeechRecognitionV2.ts'

Write-Host "Checking persistent GPT Realtime ASR contract at $BaseUrl ..."
$status = Invoke-RestMethod -Uri "$BaseUrl/api/realtime/status" -Method Get

if (-not $status.ok) { throw "Realtime status endpoint did not return ok=true." }
if ($status.transport -ne "webrtc") { throw "Expected transport=webrtc, got '$($status.transport)'." }
if ($status.turn_mode -ne "push_to_talk") { throw "Expected turn_mode=push_to_talk, got '$($status.turn_mode)'." }
if (-not $status.legacy_browser_asr_preserved) {
    throw "The legacy Browser SpeechRecognition path is not marked as preserved."
}

$runtime = Get-Content -Raw -Encoding UTF8 $RuntimeSource
$recognition = Get-Content -Raw -Encoding UTF8 $RecognitionSource

$runtimePatterns = @(
    'navigator.mediaDevices.getUserMedia',
    'createMediaStreamDestination',
    'pc.addTrack(this.silentTrack, this.silentStream)',
    'this.sender.replaceTrack(track)',
    "type: 'input_audio_buffer.commit'",
    "event.type === 'input_audio_buffer.committed'",
    'restoreSilentTrack',
    'COMMIT_TIMEOUT_MS',
    'RTP_DRAIN_MS',
    'response.output_audio_transcript.delta',
    'output_audio_buffer.started',
    'output_audio_buffer.stopped'
)
foreach ($pattern in $runtimePatterns) {
    if (-not $runtime.Contains($pattern)) {
        throw "Missing persistent Realtime audio contract: $pattern"
    }
}

$recognitionPatterns = @(
    'getRealtimeAgentRuntime',
    '.stopOutput()',
    '.then(() => agent.beginCapture())',
    '.endCapture()',
    'sender.replaceTrack(null)',
    "window.addEventListener('woodfloor:realtime-connected'"
)
foreach ($pattern in $recognitionPatterns) {
    if (-not $recognition.Contains($pattern)) {
        throw "Missing persistent push-to-talk wrapper contract: $pattern"
    }
}

$forbiddenRecognitionPatterns = @(
    'new RTCPeerConnection',
    'connectWithTrack',
    'this.stopMicrophone()'
)
foreach ($pattern in $forbiddenRecognitionPatterns) {
    if ($recognition.Contains($pattern)) {
        throw "Per-turn Realtime transport remains in the SpeechRecognition wrapper: $pattern"
    }
}

Write-Host "Persistent GPT Realtime ASR status and source contracts passed." -ForegroundColor Green
Write-Host "Configured: $($status.configured)"
Write-Host "Enabled:    $($status.enabled)"
Write-Host "Model:      $($status.model)"
Write-Host "Transport:  $($status.transport)"
Write-Host "Turn mode:  $($status.turn_mode)"
Write-Host "One negotiated session is reused; the physical microphone is attached only during push-to-talk."
Write-Host "The idle sender track is detached after negotiation so silence is not continuously uploaded."

if (-not $status.configured) {
    Write-Warning "Realtime is not ready until OPENAI_API_KEY is present in the Backend process."
}
