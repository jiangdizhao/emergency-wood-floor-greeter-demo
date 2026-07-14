param(
    [int]$Port = 8010,
    [string]$HostAddress = '127.0.0.1',
    [string]$CondaEnvName = 'kokoro-tts',
    [string]$PythonExe = '',
    [double]$ChineseSpeed = 0.84,
    [double]$EnglishSpeed = 0.92,
    [int]$ChineseChunkChars = 48
)

$ErrorActionPreference = 'Stop'
$InvariantCulture = [System.Globalization.CultureInfo]::InvariantCulture

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

if ($ChineseSpeed -lt 0.65 -or $ChineseSpeed -gt 1.25) {
    throw 'ChineseSpeed must be between 0.65 and 1.25.'
}
if ($EnglishSpeed -lt 0.65 -or $EnglishSpeed -gt 1.25) {
    throw 'EnglishSpeed must be between 0.65 and 1.25.'
}
if ($ChineseChunkChars -lt 24 -or $ChineseChunkChars -gt 96) {
    throw 'ChineseChunkChars must be between 24 and 96.'
}

$resolvedPython = Resolve-KokoroPython -ExplicitPythonExe $PythonExe -EnvName $CondaEnvName

# These variables are inherited by the Uvicorn process launched below.
$env:KOKORO_ZH_SPEED = $ChineseSpeed.ToString($InvariantCulture)
$env:KOKORO_EN_SPEED = $EnglishSpeed.ToString($InvariantCulture)
$env:KOKORO_ZH_MAX_CHARS = $ChineseChunkChars.ToString($InvariantCulture)
$env:KOKORO_LEGACY_SPEED_ONE_USES_DEFAULT = 'true'

Write-Host 'Starting local Kokoro TTS server...' -ForegroundColor Green
Write-Host "Host: $HostAddress" -ForegroundColor Cyan
Write-Host "Port: $Port" -ForegroundColor Cyan
Write-Host "Health: http://${HostAddress}:${Port}/health" -ForegroundColor Cyan
Write-Host "Conda env: $CondaEnvName" -ForegroundColor Cyan
Write-Host "Python: $resolvedPython" -ForegroundColor Cyan
Write-Host "Mandarin speed: $($env:KOKORO_ZH_SPEED) (lower is slower)" -ForegroundColor Cyan
Write-Host "English speed: $($env:KOKORO_EN_SPEED) (lower is slower)" -ForegroundColor Cyan
Write-Host "Mandarin max characters per chunk: $ChineseChunkChars" -ForegroundColor Cyan
Write-Host ''

Write-Host 'Python executable:' -ForegroundColor Yellow
& $resolvedPython -c "import sys; print(sys.executable)"
Write-Host 'SoundFile module:' -ForegroundColor Yellow
& $resolvedPython -c "import soundfile, sys; print(soundfile.__file__)"
Write-Host 'Uvicorn module:' -ForegroundColor Yellow
& $resolvedPython -c "import uvicorn, sys; print(uvicorn.__file__)"
Write-Host ''

& $resolvedPython -m uvicorn kokoro_tts_server:app --host $HostAddress --port $Port
