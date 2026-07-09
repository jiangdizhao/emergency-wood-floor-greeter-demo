param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

Write-Host "Setting console encoding to UTF-8..." -ForegroundColor Cyan
chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Read-Utf8Json {
    param(
        [Parameter(Mandatory = $true)][string]$Uri
    )

    # Invoke-RestMethod can still misdecode Chinese on some Windows PowerShell setups.
    # This function reads raw bytes and decodes them explicitly as UTF-8.
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

function Post-Json {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][hashtable]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 10
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $bytes = $utf8NoBom.GetBytes($json)

    return Invoke-RestMethod -Uri $Uri `
        -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body $bytes
}

Write-Host "\n[1] Health check" -ForegroundColor Green
Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method Get | Format-List

Write-Host "\n[2] Encoding debug endpoint" -ForegroundColor Green
$encoding = Read-Utf8Json -Uri "$BaseUrl/api/debug/encoding"
Write-Host "Content-Type: $($encoding.ContentType)"
$encoding.Json | ConvertTo-Json -Depth 10

Write-Host "\n[3] Product names decoded as UTF-8" -ForegroundColor Green
$productNames = Read-Utf8Json -Uri "$BaseUrl/api/debug/product-names"
$productNames.Json | ConvertTo-Json -Depth 10

Write-Host "\n[4] Simulate person close" -ForegroundColor Green
Post-Json -Uri "$BaseUrl/api/demo/event" -Payload @{ event = "person_close" } | ConvertTo-Json -Depth 10

Write-Host "\n[5] Simulate voice greeting" -ForegroundColor Green
Post-Json -Uri "$BaseUrl/api/greeting/voice" -Payload @{ text = "你好" } | ConvertTo-Json -Depth 10

Write-Host "\n[6] Chat / recommendation" -ForegroundColor Green
Post-Json -Uri "$BaseUrl/api/chat" -Payload @{ text = "家里有宠物，客厅用，现代简约，预算中等，哪种地板好打理？" } | ConvertTo-Json -Depth 10

Write-Host "\n[7] Compare products" -ForegroundColor Green
Post-Json -Uri "$BaseUrl/api/products/compare" -Payload @{ product_ids = @("WF-SPC-001", "WF-WOOD-002") } | ConvertTo-Json -Depth 10

Write-Host "\nSmoke test completed." -ForegroundColor Cyan
