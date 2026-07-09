# OpenAI TTS local setup

This demo uses the backend as a proxy for OpenAI TTS so the API key is never exposed in the React frontend.

## 1. Set the API key locally

PowerShell:

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate woodfloor
$env:OPENAI_API_KEY="sk-your-real-key-here"
$env:OPENAI_TTS_MODEL="gpt-4o-mini-tts"
$env:OPENAI_TTS_VOICE="marin"
uvicorn app.main:app --reload --port 8000
```

Do not commit `.env` or any real key. `.gitignore` excludes `.env` files.

## 2. Check backend TTS status

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/tts/status" -Method Get | ConvertTo-Json -Depth 10
```

Expected:

```json
{
  "openai_tts_configured": true,
  "model": "gpt-4o-mini-tts",
  "voice": "marin"
}
```

## 3. Smoke test TTS

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_tts.ps1
```

This saves an `openai_tts_test.mp3` file locally.

## 4. Frontend behavior

The UI has a `TTS Provider` selector:

- `OpenAI with browser fallback`: default; tries backend `/api/tts`, then browser TTS if OpenAI is not configured or fails.
- `OpenAI only`: uses `/api/tts` only.
- `Browser only`: uses `window.speechSynthesis` only.

## 5. English answer cleanup

When the selected conversation language is English, backend chat answers use English product display names and English selling points, so TTS no longer has to read Chinese product names or Chinese feature labels.
