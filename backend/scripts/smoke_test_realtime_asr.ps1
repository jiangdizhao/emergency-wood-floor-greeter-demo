param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RepoRoot = (Resolve-Path (Join-Path $BackendRoot '..')).Path
$RealtimeSource = Join-Path $RepoRoot 'ui\src\realtimeSpeechRecognitionV2.ts'

Write-Host "Checking GPT Realtime ASR contract at $BaseUrl ..."
$status = Invoke-RestMethod -Uri "$BaseUrl/api/realtime/status" -Method Get

if (-not $status.ok) {
    throw "Realtime status endpoint did not return ok=true."
}
if ($status.transport -ne "webrtc") {
    throw "Expected transport=webrtc, got '$($status.transport)'."
}
if ($status.turn_mode -ne "push_to_talk") {
    throw "Expected turn_mode=push_to_talk, got '$($status.turn_mode)'."
}
if (-not $status.legacy_browser_asr_preserved) {
    throw "The legacy Browser SpeechRecognition path is not marked as preserved."
}
if ($status.output_modalities -notcontains "text") {
    throw "Realtime ASR must return text so the existing Terra/Qwen chat path remains authoritative."
}

$source = Get-Content -Raw -Encoding UTF8 $RealtimeSource
$requiredPatterns = @(
    'navigator.mediaDevices.getUserMedia',
    'pc.addTrack(track, stream)',
    "this.send({ type: 'input_audio_buffer.commit' })",
    "event.type === 'input_audio_buffer.committed'",
    'void this.stopMicrophone()',
    'COMMIT_TIMEOUT_MS',
    'RTP_DRAIN_MS',
    'await this.connectWithTrack(this.track, this.stream)'
)
foreach ($pattern in $requiredPatterns) {
    if (-not $source.Contains($pattern)) {
        throw "Missing Realtime push-to-talk audio contract: $pattern"
    }
}

$forbiddenPatterns = @(
    "pc.addTransceiver('audio', { direction: 'sendonly' })",
    'replaceTrack(track)'
)
foreach ($pattern in $forbiddenPatterns) {
    if ($source.Contains($pattern)) {
        throw "Unsafe zero-audio-buffer pattern remains: $pattern"
    }
}

$micIndex = $source.IndexOf('navigator.mediaDevices.getUserMedia')
$connectIndex = $source.IndexOf('await this.connectWithTrack(this.track, this.stream)')
$commitIndex = $source.IndexOf("this.send({ type: 'input_audio_buffer.commit' })")
$commitAckIndex = $source.IndexOf("event.type === 'input_audio_buffer.committed'")
$stopMicIndex = $source.IndexOf('void this.stopMicrophone()', $commitAckIndex)
if ($micIndex -lt 0 -or $connectIndex -lt 0 -or $micIndex -gt $connectIndex) {
    throw 'Microphone must be opened before the WebRTC offer is created.'
}
if ($commitIndex -lt 0 -or $commitAckIndex -lt 0 -or $stopMicIndex -lt $commitAckIndex) {
    throw 'Realtime must keep the microphone attached through commit and stop it only after server acknowledgement.'
}

Write-Host "GPT Realtime ASR status and source contracts passed." -ForegroundColor Green
Write-Host "Configured: $($status.configured)"
Write-Host "Enabled:    $($status.enabled)"
Write-Host "Model:      $($status.model)"
Write-Host "Transport:  $($status.transport)"
Write-Host "Turn mode:  $($status.turn_mode)"
Write-Host "Audio path: the real microphone track is present in the initial SDP, and commit waits for server acknowledgement."

if (-not $status.configured) {
    Write-Warning "Realtime is not ready until OPENAI_API_KEY is present in the Backend process."
}
