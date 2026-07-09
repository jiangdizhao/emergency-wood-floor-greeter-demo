param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

Write-Host "Setting console encoding to UTF-8..." -ForegroundColor Cyan
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Show-Section {
    param([Parameter(Mandatory = $true)][string]$Title)
    Write-Host ""
    Write-Host $Title -ForegroundColor Green
}

function Read-Utf8Json {
    param(
        [Parameter(Mandatory = $true)][string]$Uri
    )

    # Invoke-RestMethod can still misdecode UTF-8 Chinese on some Windows
    # PowerShell setups. This function reads raw bytes and decodes them
    # explicitly as UTF-8.
    $resp = Invoke-WebRequest -Uri $Uri -UseBasicParsing
    $contentType = $resp.Headers["Content-Type"]

    $reader = New-Object System.IO.StreamReader($resp.RawContentStream, [System.Text.Encoding]::UTF8)
    $text = $reader.ReadToEnd()

    return [PSCustomObject]@{
        ContentType = $contentType
        Text = $text
        Json = $text | ConvertFrom-Json
    }
}

function Post-RawJson {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Json
    )

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $bytes = $utf8NoBom.GetBytes($Json)

    return Invoke-RestMethod -Uri $Uri `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body $bytes
}

Show-Section "[1] Health check"
Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get | Format-List

Show-Section "[2] Encoding debug endpoint"
$encoding = Read-Utf8Json -Uri "$BaseUrl/api/debug/encoding"
Write-Host "Content-Type: $($encoding.ContentType)"
$encoding.Json | ConvertTo-Json -Depth 10

Show-Section "[3] Product names decoded as UTF-8"
$productNames = Read-Utf8Json -Uri "$BaseUrl/api/debug/product-names"
$productNames.Json | ConvertTo-Json -Depth 10

Show-Section "[4] Simulate person close"
Post-RawJson -Uri "$BaseUrl/api/demo/event" -Json '{"event":"person_close"}' | ConvertTo-Json -Depth 10

Show-Section "[5] Simulate voice greeting"
# JSON \u escapes keep this PS1 source ASCII-only for Windows PowerShell 5.1.
# Server receives: {"text":"你好"}
Post-RawJson -Uri "$BaseUrl/api/greeting/voice" -Json '{"text":"\u4f60\u597d"}' | ConvertTo-Json -Depth 10

Show-Section "[6] Chat / recommendation"
# Server receives: {"text":"家里有宠物，客厅用，现代简约，预算中等，哪种地板好打理？"}
$chatJson = '{"text":"\u5bb6\u91cc\u6709\u5ba0\u7269\uff0c\u5ba2\u5385\u7528\uff0c\u73b0\u4ee3\u7b80\u7ea6\uff0c\u9884\u7b97\u4e2d\u7b49\uff0c\u54ea\u79cd\u5730\u677f\u597d\u6253\u7406\uff1f"}'
Post-RawJson -Uri "$BaseUrl/api/chat" -Json $chatJson | ConvertTo-Json -Depth 10

Show-Section "[7] Compare products"
Post-RawJson -Uri "$BaseUrl/api/products/compare" -Json '{"product_ids":["WF-SPC-001","WF-WOOD-002"]}' | ConvertTo-Json -Depth 10

Write-Host ""
Write-Host "Smoke test completed." -ForegroundColor Cyan
