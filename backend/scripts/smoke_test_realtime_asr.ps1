param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

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

Write-Host "GPT Realtime ASR status contract passed." -ForegroundColor Green
Write-Host "Configured: $($status.configured)"
Write-Host "Enabled:    $($status.enabled)"
Write-Host "Model:      $($status.model)"
Write-Host "Transport:  $($status.transport)"
Write-Host "Turn mode:  $($status.turn_mode)"

if (-not $status.configured) {
    Write-Warning "Realtime is not ready until OPENAI_API_KEY is present in the Backend process."
}
