param(
    [string]$PythonExecutable = "python"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$checkScript = Join-Path $scriptDir "static_check_senior_sales.py"

Write-Host "Running senior sales phase-one offline check..."
Write-Host "Backend: $backendDir"
Write-Host "Python:  $PythonExecutable"

Push-Location $backendDir
try {
    & $PythonExecutable $checkScript
    if ($LASTEXITCODE -ne 0) {
        throw "Senior sales phase-one check failed with exit code $LASTEXITCODE."
    }
    Write-Host "Senior sales phase-one check completed successfully."
}
finally {
    Pop-Location
}
