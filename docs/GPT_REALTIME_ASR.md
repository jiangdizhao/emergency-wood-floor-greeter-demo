# GPT Realtime 2.1 contextual speech recognition

This feature adds a second speech-recognition path without removing the existing browser Web Speech implementation.

## What changes

- **Browser recognition (legacy):** unchanged and remains the default.
- **GPT Realtime 2.1 recognition:** optional WebRTC push-to-talk path.
- GPT Realtime listens to the complete audio turn, resolves contextual acoustic ambiguity and user self-corrections, then returns only a normalized transcript.
- The normalized transcript continues through the existing `/api/chat` route, so the selected Terra or Qwen dialogue provider, deterministic recommendation logic, CRM policy, and Kokoro/OpenAI/browser TTS chain remain unchanged.
- The browser never receives the permanent OpenAI API key. The Backend creates the WebRTC session through `/api/realtime/session`.

## Backend configuration

Set these variables in the same PowerShell process that starts Uvicorn:

```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
$env:OPENAI_REALTIME_ENABLED="true"
$env:OPENAI_REALTIME_MODEL="gpt-realtime-2.1"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

`OPENAI_REALTIME_MODEL` is configurable so the deployment can pin another compatible Realtime model when required.

## Frontend

```powershell
cd ui
npm run build
npm run dev -- --host 127.0.0.1
```

Start a consultation. A **语音识别** selector appears in the lower-right corner:

- `浏览器识别（原方法）`
- `GPT Realtime 2.1（上下文纠错）`

The selector is disabled while recording. GPT Realtime keeps the existing button workflow:

1. Click **点击说话** to open the microphone.
2. Speak the whole turn, including any correction.
3. Click **停止说话** to close the microphone and submit the committed audio turn.
4. GPT Realtime returns the normalized user utterance; the existing chat pipeline answers it.

The microphone track is disabled between turns. The WebRTC session may remain connected for lower startup latency, but idle exhibition noise is not deliberately submitted as user audio.

## Primary correction test

Test this as one complete turn:

> 我喜欢钱会色，不，浅灰色，深浅的浅，灰色的灰。

Expected normalized transcript:

> 我喜欢浅灰色

Then compare the same recording in both ASR modes. The important metric is the final customer preference stored by the existing backend, not merely the live subtitle.

Also test:

- `我想要深灰色，不对，是浅灰色。`
- `不是原木色，我说的是浅灰。`
- `I prefer dark grey—sorry, light grey.`
- The same phrases with exhibition noise played from a nearby speaker.

## Status and smoke test

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/realtime/status | ConvertTo-Json -Depth 10
powershell -ExecutionPolicy Bypass -File .\backend\scripts\smoke_test_realtime_asr.ps1
```

The smoke test checks the server contract only. A real microphone, browser permission, network access and OpenAI account access are still required for end-to-end validation.

## Privacy and safety boundaries

- The Backend hashes the local session identifier before sending an OpenAI safety identifier.
- Recent visible conversation is used only as short-lived recognition context and phone/email-like strings are redacted by the frontend before they are included.
- Realtime is used only as a speech-understanding layer in this version; it does not choose products, write CRM data, or execute tools.
- Selecting Realtime never silently changes Terra to Qwen or Qwen to Terra.
