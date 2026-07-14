param(
    [string]$HostAddress = '127.0.0.1',
    [int]$Port = 8000,
    [string]$CondaEnvName = 'smartoffice',
    [string]$PythonExe = '',
    [string]$Model = 'gpt-5.6-terra',
    [int]$ParseTimeoutSeconds = 12,
    [int]$RenderTimeoutSeconds = 15,
    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'

function Resolve-BackendPython {
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

function Set-OpenAIKeyFromSecurePrompt {
    if (-not [string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
        return
    }

    $secureKey = Read-Host 'OpenAI API key' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    try {
        $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        if ([string]::IsNullOrWhiteSpace($plainKey)) {
            throw 'OPENAI_API_KEY was empty.'
        }
        $env:OPENAI_API_KEY = $plainKey
    }
    finally {
        if ($bstr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
        Remove-Variable secureKey -ErrorAction SilentlyContinue
        Remove-Variable plainKey -ErrorAction SilentlyContinue
    }
}

$resolvedPython = Resolve-BackendPython -ExplicitPythonExe $PythonExe -EnvName $CondaEnvName
Set-OpenAIKeyFromSecurePrompt

if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    throw 'OPENAI_API_KEY is not configured. Terra cannot start.'
}

$env:DEFAULT_DIALOGUE_PROVIDER = 'terra'
$env:OPENAI_DIALOGUE_MODEL = $Model
$env:OPENAI_PARSE_TIMEOUT_SECONDS = $ParseTimeoutSeconds.ToString()
$env:OPENAI_RENDER_TIMEOUT_SECONDS = $RenderTimeoutSeconds.ToString()
$env:LOCAL_TTS_URL = if ($env:LOCAL_TTS_URL) { $env:LOCAL_TTS_URL } else { 'http://127.0.0.1:8010/tts' }
$env:LOCAL_TTS_HEALTH_URL = if ($env:LOCAL_TTS_HEALTH_URL) { $env:LOCAL_TTS_HEALTH_URL } else { 'http://127.0.0.1:8010/health' }

Write-Host 'Starting Backend in Terra mode...' -ForegroundColor Green
Write-Host "Host: $HostAddress" -ForegroundColor Cyan
Write-Host "Port: $Port" -ForegroundColor Cyan
Write-Host "Python: $resolvedPython" -ForegroundColor Cyan
Write-Host "Model: $Model" -ForegroundColor Cyan
Write-Host 'OPENAI_API_KEY: configured (value hidden)' -ForegroundColor Cyan
Write-Host "Local TTS: $($env:LOCAL_TTS_URL)" -ForegroundColor Cyan
Write-Host ''

$arguments = @(
    '-m', 'uvicorn', 'app.main:app',
    '--host', $HostAddress,
    '--port', $Port.ToString()
)
if (-not $NoReload) {
    $arguments += '--reload'
}

& $resolvedPython @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Backend exited with code $LASTEXITCODE."
}
