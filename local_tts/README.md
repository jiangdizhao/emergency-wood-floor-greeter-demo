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

## Smoke test local Kokoro

Open another terminal:

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1
```

Chinese smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1 -Language zh -OutFile .\kokoro_zh_test.wav
```

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

The frontend `TTS Provider` selector supports:

- `Local Kokoro → OpenAI → Browser`: default auto mode.
- `Local Kokoro only`.
- `OpenAI only`.
- `Browser only`.

In auto mode, the main backend tries local Kokoro first. If local Kokoro is not running or fails, it tries OpenAI TTS. If that also fails, the frontend falls back to browser TTS.

## Voices

Default voices are controlled by environment variables in the local Kokoro service process:

```powershell
$env:KOKORO_EN_VOICE="af_heart"
$env:KOKORO_ZH_VOICE="zf_xiaobei"
```

The defaults match the voices used in the earlier manual tests. If a voice is unavailable in your installed Kokoro package, change the corresponding environment variable before starting the local service.
