param(
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [ValidateSet("terra", "qwen")]
    [string]$ProviderMode = "qwen",
    [switch]$RunRecognition
)

$ErrorActionPreference = "Stop"
$BackendUrl = $BackendUrl.TrimEnd("/")

function Show-Json {
    param([Parameter(Mandatory = $true)]$Value)
    $Value | ConvertTo-Json -Depth 30
}

function Invoke-Utf8JsonPost {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][hashtable]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 30 -Compress
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json; charset=utf-8" -Body $bodyBytes
}

# Keep this script ASCII-only so Windows PowerShell 5.1 does not misread a
# UTF-8-without-BOM source file. Convert the Chinese chat sample from JSON
# Unicode escapes at runtime instead.
$chatText = '"\u5ba2\u5385\u7528\uff0c\u9884\u7b97\u4e2d\u7b49\uff0c\u559c\u6b22\u73b0\u4ee3\u7b80\u7ea6\u3002"' | ConvertFrom-Json

Write-Host "=== 1. Backend health ==="
$health = Invoke-RestMethod -Uri "${BackendUrl}/api/health" -Method Get
Show-Json -Value $health

Write-Host ""
Write-Host "=== 2. Face identity status ==="
$identity = Invoke-RestMethod -Uri "${BackendUrl}/api/identity/status" -Method Get
Show-Json -Value $identity

if (-not $identity.model.available) {
    Write-Warning "Face models are not ready. Run: powershell -ExecutionPolicy Bypass -File .\scripts\download_face_models.ps1"
    exit 2
}

Write-Host ""
Write-Host "=== 3. Create a fresh anonymous visit session ==="
$newSession = Invoke-Utf8JsonPost -Uri "${BackendUrl}/api/identity/session/new" -Payload @{
    provider_mode = $ProviderMode
}
Show-Json -Value $newSession

if (-not $newSession.session_id) {
    throw "New identity-aware session did not return session_id."
}
if ($newSession.customer_profile.session_id -ne $newSession.session_id) {
    throw "Customer profile session_id does not match the visit session."
}

Write-Host ""
Write-Host "=== 4. Confirm dynamic session works with chat ==="
$chat = Invoke-Utf8JsonPost -Uri "${BackendUrl}/api/chat" -Payload @{
    session_id = $newSession.session_id
    response_language = "zh"
    text = $chatText
}
Show-Json -Value $chat

if ($chat.customer_profile.session_id -ne $newSession.session_id) {
    throw "Chat response lost the dynamic session_id."
}

if ($RunRecognition) {
    Write-Host ""
    Write-Host "=== 5. Multi-frame recognition ==="
    Write-Host "Face the camera and keep still."
    Start-Sleep -Seconds 1

    $recognition = Invoke-Utf8JsonPost -Uri "${BackendUrl}/api/identity/recognize" -Payload @{
        provider_mode = $ProviderMode
    }
    Show-Json -Value $recognition
}

Write-Host ""
Write-Host "Smoke test completed."
Write-Host "Enrollment is intentionally not automated because it requires explicit customer consent and a live face."
