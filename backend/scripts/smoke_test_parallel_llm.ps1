param(
    [ValidateSet("terra", "qwen")]
    [string]$ProviderMode = "qwen",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$SessionId = "demo-session-001"
)

$ErrorActionPreference = "Stop"
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Post-Utf8Json {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][hashtable]$Body
    )
    $json = $Body | ConvertTo-Json -Depth 20 -Compress
    $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($json)
    return Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes
}

Write-Host "[1] LLM provider status" -ForegroundColor Cyan
Invoke-RestMethod -Uri "$BaseUrl/api/llm/status?session_id=$SessionId" -Method Get | ConvertTo-Json -Depth 20

Write-Host "`n[2] Select provider: $ProviderMode" -ForegroundColor Cyan
Post-Utf8Json -Uri "$BaseUrl/api/session/provider" -Body @{
    session_id = $SessionId
    provider_mode = $ProviderMode
} | ConvertTo-Json -Depth 20

Write-Host "`n[3] Reset customer profile (provider selection is preserved)" -ForegroundColor Cyan
Invoke-RestMethod -Uri "$BaseUrl/api/session/reset?session_id=$SessionId" -Method Post | ConvertTo-Json -Depth 20

Write-Host "`n[4] Complex recommendation turn" -ForegroundColor Cyan
Post-Utf8Json -Uri "$BaseUrl/api/chat" -Body @{
    session_id = $SessionId
    provider_mode = $ProviderMode
    response_language = "zh"
    text = "客厅用，家里有两只猫，预算中等，耐磨和好清洁最重要，请推荐一下。"
} | ConvertTo-Json -Depth 30

Write-Host "`n[5] Correction / negation turn" -ForegroundColor Cyan
Post-Utf8Json -Uri "$BaseUrl/api/chat" -Body @{
    session_id = $SessionId
    provider_mode = $ProviderMode
    response_language = "zh"
    text = "刚才说有宠物不对，家里其实没养猫也没养狗。"
} | ConvertTo-Json -Depth 30

Write-Host "`nParallel LLM smoke test completed in $ProviderMode mode." -ForegroundColor Green
