param(
    [string]$CondaEnvironment = "smartoffice",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Split-Path -Parent $scriptDir
$checkScript = Join-Path $scriptDir "static_check_senior_sales.py"

function Resolve-CondaExecutable {
    $candidates = @()

    if ($env:CONDA_EXE) {
        $candidates += $env:CONDA_EXE
    }

    $condaCommand = Get-Command conda.exe -ErrorAction SilentlyContinue
    if ($condaCommand) {
        $candidates += $condaCommand.Source
    }

    $condaBatCommand = Get-Command conda.bat -ErrorAction SilentlyContinue
    if ($condaBatCommand) {
        $candidates += $condaBatCommand.Source
    }

    $candidates += @(
        "D:\anaconda3\Scripts\conda.exe",
        "D:\anaconda3\condabin\conda.bat",
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe",
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe"
    )

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    throw "Unable to find conda.exe or conda.bat. Pass -PythonExecutable with the full path to the smartoffice python.exe."
}

Write-Host "Running senior sales phase-one offline check..."
Write-Host "Backend: $backendDir"

Push-Location $backendDir
try {
    if ($PythonExecutable) {
        if (-not (Test-Path $PythonExecutable)) {
            throw "Python executable does not exist: $PythonExecutable"
        }

        Write-Host "Execution mode: explicit Python"
        Write-Host "Python: $PythonExecutable"
        & $PythonExecutable $checkScript
    }
    else {
        $condaExecutable = Resolve-CondaExecutable
        Write-Host "Execution mode: conda run"
        Write-Host "Conda: $condaExecutable"
        Write-Host "Environment: $CondaEnvironment"

        # `conda activate` is a shell function and cannot be performed reliably by
        # launching conda.exe directly. `conda run` selects the requested environment
        # without requiring `conda init`, and also avoids a child PowerShell profile
        # silently resolving `python` to the base Anaconda interpreter.
        & $condaExecutable run --no-capture-output -n $CondaEnvironment python $checkScript
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Senior sales phase-one check failed with exit code $LASTEXITCODE."
    }

    Write-Host "Senior sales phase-one check completed successfully."
}
finally {
    Pop-Location
}
