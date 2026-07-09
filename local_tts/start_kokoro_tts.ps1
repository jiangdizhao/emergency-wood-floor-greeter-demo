param(
    [int]$Port = 8010,
    [string]$HostAddress = '127.0.0.1',
    [string]$CondaEnvName = 'kokoro-tts',
    [string]$PythonExe = ''
)

$ErrorActionPreference = 'Stop'

function Resolve-KokoroPython {
    param(
        [string]$ExplicitPythonExe,
        [string]$EnvName
    )

    if ($ExplicitPythonExe -and (Test-Path $ExplicitPythonExe)) {
        return (Resolve-Path $ExplicitPythonExe).Path
    }

    if ($env:CONDA_PREFIX) {
        $candidate = Join-Path $env:CONDA_PREFIX 'python.exe'
        if ((Test-Path $candidate) -and ($candidate -match "envs[\\/]$EnvName[\\/]python\.exe$")) {
            return $candidate
        }
    }

    $condaBase = $null
    try {
        $condaBase = (& conda info --base 2>$null).Trim()
    } catch {
        $condaBase = $null
    }

    if ($condaBase) {
        $candidate = Join-Path $condaBase "envs\$EnvName\python.exe"
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $commonCandidates = @(
        "D:\anaconda3\envs\$EnvName\python.exe",
        "C:\ProgramData\anaconda3\envs\$EnvName\python.exe",
        "$env:USERPROFILE\anaconda3\envs\$EnvName\python.exe",
        "$env:USERPROFILE\miniconda3\envs\$EnvName\python.exe"
    )

    foreach ($candidate in $commonCandidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "Cannot find python.exe for conda env '$EnvName'. Pass -PythonExe 'D:\anaconda3\envs\$EnvName\python.exe'."
}

$resolvedPython = Resolve-KokoroPython -ExplicitPythonExe $PythonExe -EnvName $CondaEnvName

Write-Host 'Starting local Kokoro TTS server...' -ForegroundColor Green
Write-Host "Host: $HostAddress" -ForegroundColor Cyan
Write-Host "Port: $Port" -ForegroundColor Cyan
Write-Host "Health: http://${HostAddress}:${Port}/health" -ForegroundColor Cyan
Write-Host "Conda env: $CondaEnvName" -ForegroundColor Cyan
Write-Host "Python: $resolvedPython" -ForegroundColor Cyan
Write-Host ''

Write-Host 'Python executable:' -ForegroundColor Yellow
& $resolvedPython -c "import sys; print(sys.executable)"
Write-Host 'SoundFile module:' -ForegroundColor Yellow
& $resolvedPython -c "import soundfile, sys; print(soundfile.__file__)"
Write-Host 'Uvicorn module:' -ForegroundColor Yellow
& $resolvedPython -c "import uvicorn, sys; print(uvicorn.__file__)"
Write-Host ''

& $resolvedPython -m uvicorn kokoro_tts_server:app --host $HostAddress --port $Port
