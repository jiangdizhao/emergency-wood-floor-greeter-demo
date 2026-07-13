param(
    [string]$CondaEnvName = "smartoffice",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$checkScript = Join-Path $scriptDir "static_check_bilingual.py"

Write-Host "Running bilingual UI and speech offline check..." -ForegroundColor Green
Write-Host "Backend: $backendDir" -ForegroundColor Cyan

Push-Location $backendDir
try {
    if ($PythonExecutable) {
        Write-Host "Execution mode: explicit Python" -ForegroundColor Cyan
        Write-Host "Python: $PythonExecutable" -ForegroundColor Cyan
        & $PythonExecutable $checkScript
    }
    else {
        $condaCommand = Get-Command conda -ErrorAction SilentlyContinue
        if (-not $condaCommand) {
            throw "Conda was not found. Pass -PythonExecutable with the smartoffice environment python.exe path."
        }
        Write-Host "Execution mode: conda run" -ForegroundColor Cyan
        Write-Host "Conda: $($condaCommand.Source)" -ForegroundColor Cyan
        Write-Host "Environment: $CondaEnvName" -ForegroundColor Cyan
        & conda run --no-capture-output -n $CondaEnvName python $checkScript
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Bilingual feature check failed with exit code $LASTEXITCODE."
    }
    Write-Host "Bilingual UI and speech check completed successfully." -ForegroundColor Green
}
finally {
    Pop-Location
}
