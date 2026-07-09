param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"

Write-Host "[1] Start vision service" -ForegroundColor Green
Invoke-RestMethod -Uri "$BaseUrl/api/vision/start" -Method Post | ConvertTo-Json -Depth 10

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "[2] Check vision status" -ForegroundColor Green
Invoke-RestMethod -Uri "$BaseUrl/api/vision/status" -Method Get | ConvertTo-Json -Depth 10

Write-Host ""
Write-Host "[3] Open this URL in browser to view MJPEG stream:" -ForegroundColor Green
Write-Host "$BaseUrl/api/vision/stream"

Write-Host ""
Write-Host "[4] Keep the browser stream open. Move close to the camera and wave." -ForegroundColor Yellow
Write-Host "Press Enter after testing to stop the vision service."
Read-Host | Out-Null

Write-Host ""
Write-Host "[5] Stop vision service" -ForegroundColor Green
Invoke-RestMethod -Uri "$BaseUrl/api/vision/stop" -Method Post | ConvertTo-Json -Depth 10
