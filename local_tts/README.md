# Local Kokoro TTS service

This service runs in a separate conda environment so the verified `woodfloor` vision/backend environment is not polluted by Kokoro or PyTorch dependencies.

## Recommended runtime layout

Terminal 1: local Kokoro TTS service in `kokoro-tts` env.

Terminal 2: main FastAPI backend in `woodfloor` env.

Terminal 3: React frontend.

The main backend calls this local service through `LOCAL_TTS_URL`.

Default local URLs:

```text
http://127.0.0.1:8010/health
http://127.0.0.1:8010/tts
```

## Start local Kokoro service

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
powershell -ExecutionPolicy Bypass -File .\start_kokoro_tts.ps1
```

If your `kokoro-tts` environment does not already include FastAPI/Uvicorn, install this service's requirements inside that env:

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
python -m pip install -r requirements.txt
```

## Startup warm-up

The service now warms the Mandarin pipeline during FastAPI startup. It loads Kokoro, loads the selected Mandarin voice, runs one real inference, and caches the exact customer welcome audio used by the frontend.

Uvicorn does not report `Application startup complete` until this warm-up has finished. This moves the cold-start delay to service startup instead of making the first customer wait after clicking `开始咨询`.

Expected startup log:

```text
Warming up Kokoro Mandarin pipeline with voice 'zm_yunxi'...
Kokoro Mandarin warm-up completed in ...s; welcome audio cached (... bytes).
INFO: Application startup complete.
```

Check warm-up state:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8010/health" -Method Get | ConvertTo-Json -Depth 10
```

Expected fields include:

```json
{
  "loaded_zh": true,
  "default_zh_voice": "zm_yunxi",
  "warmup_enabled": true,
  "warmup_ready": true,
  "warmup_error": null
}
```

Warm-up is enabled by default. It can be disabled for troubleshooting before starting the service:

```powershell
$env:KOKORO_WARMUP_ON_START="false"
```

The cached welcome audio is reused only when language, voice, speed, and text match the configured warm-up request. Other answers still use normal live synthesis.

## Smoke test local Kokoro

Open another terminal:

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1
```

Chinese smoke test using the server default voice:

```powershell
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1 `
  -Language zh `
  -OutFile .\kokoro_zh_test.wav
```

Test a specific voice:

```powershell
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1 `
  -Language zh `
  -Voice zm_yunyang `
  -OutFile .\kokoro_zm_yunyang.wav
```

## Mandarin voices

The customer-facing avatar is male, so the default Mandarin voice is now:

```text
zm_yunxi
```

Kokoro v1.0 provides four Mandarin male voices:

```text
zm_yunjian
zm_yunxi
zm_yunxia
zm_yunyang
```

It also provides four Mandarin female voices:

```text
zf_xiaobei
zf_xiaoni
zf_xiaoxiao
zf_xiaoyi
```

Generate samples for all four Mandarin male voices:

```powershell
powershell -ExecutionPolicy Bypass -File .\compare_chinese_male_voices.ps1
```

The samples are written to:

```text
local_tts\voice_samples\
```

Choose another default voice before starting the service:

```powershell
$env:KOKORO_ZH_VOICE="zm_yunyang"
powershell -ExecutionPolicy Bypass -File .\start_kokoro_tts.ps1
```

The startup warm-up automatically uses and caches whichever voice is selected through `KOKORO_ZH_VOICE`.

## Main backend integration

Start the main backend with the local TTS URL:

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate woodfloor
$env:LOCAL_TTS_URL="http://127.0.0.1:8010/tts"
$env:LOCAL_TTS_HEALTH_URL="http://127.0.0.1:8010/health"
uvicorn app.main:app --reload --port 8000
```

Then check:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/tts/status" -Method Get | ConvertTo-Json -Depth 10
```

Expected:

```json
{
  "local_tts_available": true,
  "local_tts_url": "http://127.0.0.1:8010/tts"
}
```

## Provider behavior

The customer UI uses automatic TTS mode. The main backend tries local Kokoro first. If local Kokoro is not running or fails, it tries OpenAI TTS. If that also fails, the frontend falls back to browser TTS.

## Other voice environment variables

```powershell
$env:KOKORO_EN_VOICE="af_heart"
$env:KOKORO_ZH_VOICE="zm_yunxi"
```

If a voice is unavailable in your installed Kokoro package, update the package in the isolated `kokoro-tts` environment or select another installed voice. Do not modify the verified MediaPipe/NumPy/OpenCV versions in the separate `woodfloor` environment.
