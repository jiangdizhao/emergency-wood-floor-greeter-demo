param(
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [ValidateSet("terra", "qwen")]
    [string]$ProviderMode = "qwen",
    [switch]$RunRecognition
)

$ErrorActionPreference = "Stop"

function Show-Json($value) {
    $value | ConvertTo-Json -Depth 30
}

Write-Host "=== 1. Backend health ==="
$health = Invoke-RestMethod -Uri "$BackendUrl/api/health" -Method Get
Show-Json $health

Write-Host ""
Write-Host "=== 2. Face identity status ==="
$identity = Invoke-RestMethod -Uri "$BackendUrl/api/identity/status" -Method Get
Show-Json $identity

if (-not $identity.model.available) {
    Write-Warning "Face models are not ready. Run: powershell -ExecutionPolicy Bypass -File .\scripts\download_face_models.ps1"
    exit 2
}

Write-Host ""
Write-Host "=== 3. Create a fresh anonymous visit session ==="
$newSessionBody = @{ provider_mode = $ProviderMode } | ConvertTo-Json
$newSession = Invoke-RestMethod `
    -Uri "$BackendUrl/api/identity/session/new" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body $newSessionBody
Show-Json $newSession

if (-not $newSession.session_id) {
    throw "New identity-aware session did not return session_id."
}
if ($newSession.customer_profile.session_id -ne $newSession.session_id) {
    throw "Customer profile session_id does not match the visit session."
}

Write-Host ""
Write-Host "=== 4. Confirm dynamic session works with chat ==="
$chatBody = @{
    session_id = $newSession.session_id
    response_language = "zh"
    text = "客厅用，预算中等，喜欢现代简约。"
} | ConvertTo-Json
$chat = Invoke-RestMethod `
    -Uri "$BackendUrl/api/chat" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body $chatBody
Show-Json $chat

if ($chat.customer_profile.session_id -ne $newSession.session_id) {
    throw "Chat response lost the dynamic session_id."
}

if ($RunRecognition) {
    Write-Host ""
    Write-Host "=== 5. Multi-frame recognition ==="
    Write-Host "Face the camera and keep still."
    Start-Sleep -Seconds 1
    $recognizeBody = @{ provider_mode = $ProviderMode } | ConvertTo-Json
    $recognition = Invoke-RestMethod `
        -Uri "$BackendUrl/api/identity/recognize" `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body $recognizeBody
    Show-Json $recognition
}

Write-Host ""
Write-Host "Smoke test completed."
Write-Host "Enrollment is intentionally not automated because it requires an explicit customer consent action and a live face."
