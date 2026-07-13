# One-click Chinese / English mode

The main customer UI now has a fixed language button in the upper-right corner:

```text
Chinese mode: EN
English mode: 中文
```

Changing language reloads the page and starts a clean UI rendering in the selected language. The selection is kept in browser `localStorage`.

English mode changes:

- visible customer-facing UI labels;
- quick prompts and consultant descriptions;
- Terra and Qwen response language;
- browser speech recognition from `zh-CN` to `en-US`;
- local Kokoro TTS from the four Mandarin voices to four English voices;
- browser speech-synthesis fallback language;
- product names, product comparison labels and summary values shown in the React UI.

## English consultant voices

The demo maps the existing four consultant portraits to four American English Kokoro voices:

| Consultant style | Mandarin voice | English voice |
|---|---|---|
| Warm and friendly | `zm_yunxi` | `am_liam` |
| Calm and professional | `zm_yunjian` | `am_michael` |
| Young and energetic | `zm_yunxia` | `am_puck` |
| Mature and confident | `zm_yunyang` | `am_onyx` |

These style-to-voice pairings are demo choices, not official personality labels from the Kokoro model publisher.

## Download the four English voices

```powershell
cd F:\emergency-wood-floor-greeter-demo

git pull --ff-only

powershell -ExecutionPolicy Bypass `
  -File .\local_tts\download_english_voices.ps1
```

The wrapper resolves the `kokoro-tts` environment and downloads these files from `hexgrad/Kokoro-82M` into the normal Hugging Face cache:

```text
voices/am_liam.pt
voices/am_michael.pt
voices/am_puck.pt
voices/am_onyx.pt
```

Explicit Python path:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\local_tts\download_english_voices.ps1 `
  -PythonExe "D:\anaconda3\envs\kokoro-tts\python.exe"
```

Optional custom Hugging Face cache:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\local_tts\download_english_voices.ps1 `
  -CacheDir "F:\model-cache\huggingface"
```

## Start bilingual Kokoro TTS

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts

powershell -ExecutionPolicy Bypass `
  -File .\start_kokoro_tts.ps1
```

Startup now warms the four Mandarin and four English voices before the service is considered ready. This removes most first-use delay after changing language or consultant.

Check readiness:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/health" `
  -Method Get |
ConvertTo-Json -Depth 20
```

Expected fields:

```text
warmup_zh_ready = true
warmup_en_ready = true
warmup_ready = true
```

## Direct English TTS checks

```powershell
$voices = @("am_liam", "am_michael", "am_puck", "am_onyx")

foreach ($voice in $voices) {
    $body = @{
        text = "Hello, I am your flooring consultant. I can help you compare materials, maintenance, comfort and budget."
        language = "en"
        voice = $voice
        speed = 1.0
    } | ConvertTo-Json

    Invoke-WebRequest `
      -Uri "http://127.0.0.1:8010/tts" `
      -Method Post `
      -ContentType "application/json; charset=utf-8" `
      -Body $body `
      -OutFile ".\test-$voice.wav"
}
```

The files will be written as:

```text
test-am_liam.wav
test-am_michael.wav
test-am_puck.wav
test-am_onyx.wav
```

## Offline bilingual code check

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_bilingual.ps1
```

This check does not call Terra, Qwen, Kokoro, the camera or the microphone. It verifies language routing, English sales-plan localization, voice mappings, speech-recognition switching and required UI assets.

## Manual end-to-end test

1. Start Kokoro, Backend, Ollama if using Qwen, and the Vite frontend.
2. Open `http://127.0.0.1:5173`.
3. Select `EN` in the upper-right corner.
4. Confirm that all main customer-facing labels are English.
5. Preview each of the four consultant voices.
6. Start a new consultation and speak English.
7. Confirm that browser recognition uses English and the assistant replies in English.
8. Confirm that local TTS uses the corresponding `am_*` voice.
9. Compare two products and finish the consultation summary.
10. Select `中文` and verify that the Chinese UI and `zm_*` voices return.
