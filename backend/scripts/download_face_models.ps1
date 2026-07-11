param(
    [string]$ModelDirectory = "$(Join-Path $PSScriptRoot '..\app\data\models')"
)

$ErrorActionPreference = 'Stop'

$resolvedDirectory = [System.IO.Path]::GetFullPath($ModelDirectory)
New-Item -ItemType Directory -Path $resolvedDirectory -Force | Out-Null

$models = @(
    @{
        Name = 'YuNet face detector'
        File = 'face_detection_yunet_2023mar.onnx'
        Url = 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
        MinBytes = 100000
    },
    @{
        Name = 'SFace face recognizer'
        File = 'face_recognition_sface_2021dec.onnx'
        Url = 'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx'
        MinBytes = 1000000
    }
)

foreach ($model in $models) {
    $destination = Join-Path $resolvedDirectory $model.File
    if (Test-Path $destination) {
        $existingSize = (Get-Item $destination).Length
        if ($existingSize -ge $model.MinBytes) {
            Write-Host "Already present: $($model.Name) ($existingSize bytes)"
            continue
        }
        Remove-Item $destination -Force
    }

    Write-Host "Downloading $($model.Name)..."
    Invoke-WebRequest -Uri $model.Url -OutFile $destination -UseBasicParsing
    $downloadedSize = (Get-Item $destination).Length
    if ($downloadedSize -lt $model.MinBytes) {
        Remove-Item $destination -Force -ErrorAction SilentlyContinue
        throw "Downloaded file for $($model.Name) is unexpectedly small ($downloadedSize bytes)."
    }
    Write-Host "Saved: $destination ($downloadedSize bytes)"
}

Write-Host ""
Write-Host "Face models are ready in: $resolvedDirectory"
Write-Host "Restart the backend, then check: http://127.0.0.1:8000/api/identity/status"
