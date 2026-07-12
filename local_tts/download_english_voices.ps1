param(
    [string]$CondaEnvName = "kokoro-tts",
    [string]$PythonExe = "",
    [string]$CacheDir = ""
)

$ErrorActionPreference = "Stop"

function Resolve-KokoroPython {
    param(
        [string]$ExplicitPythonExe,
        [string]$EnvName
    )

    if ($ExplicitPythonExe -and (Test-Path $ExplicitPythonExe)) {
        return (Resolve-Path $ExplicitPythonExe).Path
    }

    if ($env:CONDA_PREFIX) {
        $candidate = Join-Path $env:CONDA_PREFIX "python.exe"
        if ((Test-Path $candidate) -and ($candidate -match "envs[\\/]$EnvName[\\/]python\.exe$")) {
            return $candidate
        }
    }

    $condaBase = $null
    try {
        $condaBase = (& conda info --base 2>$null).Trim()
    }
    catch {
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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$downloader = Join-Path $scriptDir "download_english_voices.py"
$resolvedPython = Resolve-KokoroPython -ExplicitPythonExe $PythonExe -EnvName $CondaEnvName

Write-Host "Downloading Kokoro English voices..." -ForegroundColor Green
Write-Host "Python: $resolvedPython" -ForegroundColor Cyan
Write-Host "Voices: am_liam, am_michael, am_puck, am_onyx" -ForegroundColor Cyan
Write-Host "Repository: hexgrad/Kokoro-82M" -ForegroundColor Cyan
Write-Host ""

$arguments = @($downloader)
if ($CacheDir) {
    $arguments += @("--cache-dir", $CacheDir)
}

& $resolvedPython @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Kokoro English voice download failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Kokoro English voice download completed successfully." -ForegroundColor Green
