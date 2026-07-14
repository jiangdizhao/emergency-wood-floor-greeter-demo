param(
    [int]$Port = 8010,
    [string]$HostAddress = '127.0.0.1',
    [string]$CondaEnvName = 'kokoro-tts',
    [string]$PythonExe = '',
    [double]$ChineseSpeed = 0.86,
    [double]$EnglishSpeed = 0.92,
    [int]$ChineseChunkChars = 78,
    [ValidateSet('original', 'soft', 'neutral')]
    [string]$ChineseProsodyMode = 'soft'
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

    throw "Cannot find python.exe for conda env '$EnvName'. Pass -PythonExe explicitly."
}

if ($ChineseSpeed -lt 0.65 -or $ChineseSpeed -gt 1.25) {
    throw 'ChineseSpeed must be between 0.65 and 1.25.'
}
if ($EnglishSpeed -lt 0.65 -or $EnglishSpeed -gt 1.25) {
    throw 'EnglishSpeed must be between 0.65 and 1.25.'
}
if ($ChineseChunkChars -lt 24 -or $ChineseChunkChars -gt 120) {
    throw 'ChineseChunkChars must be between 24 and 120.'
}

$resolvedPython = Resolve-KokoroPython -ExplicitPythonExe $PythonExe -EnvName $CondaEnvName

$env:KOKORO_ZH_SPEED = $ChineseSpeed.ToString($InvariantCulture)
$env:KOKORO_EN_SPEED = $EnglishSpeed.ToString($InvariantCulture)
$env:KOKORO_ZH_MAX_CHARS = $ChineseChunkChars.ToString($InvariantCulture)
$env:KOKORO_ZH_PROSODY_MODE = $ChineseProsodyMode
$env:KOKORO_ZH_VOICE_SPEEDS = 'zm_yunxi=0.86,zm_yunjian=0.84,zm_yunxia=0.90,zm_yunyang=0.87'
$env:KOKORO_LEGACY_SPEED_ONE_USES_DEFAULT = 'true'
$env:KOKORO_CLAUSE_PAUSE_MS = '0'
$env:KOKORO_SENTENCE_PAUSE_MS = '0'
$env:KOKORO_TRIM_CHUNK_SILENCE = 'true'
$env:KOKORO_SILENCE_THRESHOLD_DB = '-46'
$env:KOKORO_SILENCE_PAD_MS = '20'
$env:KOKORO_CHUNK_CROSSFADE_MS = '4'

Write-Host 'Starting local Kokoro TTS server...' -ForegroundColor Green
Write-Host "Host: $HostAddress" -ForegroundColor Cyan
Write-Host "Port: $Port" -ForegroundColor Cyan
Write-Host "Health: http://${HostAddress}:${Port}/health" -ForegroundColor Cyan
Write-Host "Conda env: $CondaEnvName" -ForegroundColor Cyan
Write-Host "Python: $resolvedPython" -ForegroundColor Cyan
Write-Host "Mandarin base speed: $($env:KOKORO_ZH_SPEED)" -ForegroundColor Cyan
Write-Host "Mandarin per-voice speeds: $($env:KOKORO_ZH_VOICE_SPEEDS)" -ForegroundColor Cyan
Write-Host "English speed: $($env:KOKORO_EN_SPEED)" -ForegroundColor Cyan
Write-Host "Mandarin max characters per chunk: $ChineseChunkChars" -ForegroundColor Cyan
Write-Host "Mandarin prosody mode: $ChineseProsodyMode" -ForegroundColor Cyan
Write-Host 'Artificial punctuation silence: disabled' -ForegroundColor Cyan
Write-Host 'Chunk-edge silence trim: -46 dB threshold with 20 ms natural padding' -ForegroundColor Cyan
Write-Host 'Chunk crossfade: 4 ms' -ForegroundColor Cyan
Write-Host ''

Write-Host 'Python executable:' -ForegroundColor Yellow
& $resolvedPython -c "import sys; print(sys.executable)"
Write-Host 'SoundFile module:' -ForegroundColor Yellow
& $resolvedPython -c "import soundfile, sys; print(soundfile.__file__)"
Write-Host 'Uvicorn module:' -ForegroundColor Yellow
& $resolvedPython -c "import uvicorn, sys; print(uvicorn.__file__)"
Write-Host ''

& $resolvedPython -m uvicorn kokoro_tts_server:app --host $HostAddress --port $Port
if ($LASTEXITCODE -ne 0) {
    throw "Kokoro TTS server exited with code $LASTEXITCODE."
}
