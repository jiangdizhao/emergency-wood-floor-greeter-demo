# Emergency Wood Floor Greeter Demo

Customer-facing wood-floor retail AI assistant demo.

Current product flow:

- customer presses one clear **开始咨询** button
- the assistant greets the customer, introduces itself, and asks the first needs-discovery question
- Chinese is the default and only customer-facing conversation language for this phase
- browser Web Speech API provides push-to-talk speech recognition
- local Kokoro is the primary TTS provider, with OpenAI and browser SpeechSynthesis fallbacks
- deterministic product recommendation, comparison, customer profile extraction, and session summary remain available
- the OpenCV + MediaPipe camera service can run silently in the backend, but no camera image or engineering telemetry is shown to customers
- the customer UI uses a warm retail layout, an animated virtual consultant, and only a few primary actions

## Backend quick start

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate woodfloor
uvicorn app.main:app --reload --port 8000
```

Important: do not reinstall or downgrade the verified vision environment unless explicitly needed. The current verified environment is:

```text
mediapipe==0.10.13
numpy==2.4.6
opencv-python==4.13.0.92
```

`requirements.txt` records these user-verified versions. If the local environment already works, do not run `--force-reinstall`.

Useful backend URLs:

- API root: http://127.0.0.1:8000/
- Health: http://127.0.0.1:8000/api/health
- Docs: http://127.0.0.1:8000/docs
- Vision status: http://127.0.0.1:8000/api/vision/status
- TTS status: http://127.0.0.1:8000/api/tts/status

## Local Kokoro TTS quick start

Run Kokoro in its separate conda environment:

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
powershell -ExecutionPolicy Bypass -File .\start_kokoro_tts.ps1
```

Install the local TTS service dependencies only when needed:

```powershell
python -m pip install -r requirements.txt
```

Smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1 -Language zh -OutFile .\kokoro_zh_test.wav
```

Then start the main backend with the local Kokoro endpoints:

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate woodfloor
$env:LOCAL_TTS_URL="http://127.0.0.1:8010/tts"
$env:LOCAL_TTS_HEALTH_URL="http://127.0.0.1:8010/health"
uvicorn app.main:app --reload --port 8000
```

Check the main backend TTS status:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/tts/status" -Method Get | ConvertTo-Json -Depth 10
```

## OpenAI TTS fallback

OpenAI TTS remains an optional fallback. Set the key only in the local PowerShell session before starting the backend:

```powershell
$env:OPENAI_API_KEY="sk-your-real-key-here"
$env:OPENAI_TTS_MODEL="gpt-4o-mini-tts"
$env:OPENAI_TTS_VOICE="marin"
```

Do not commit a real key. `.env` files are ignored.

## Frontend quick start

Start Kokoro and the backend first. Then open a third terminal:

```powershell
cd F:\emergency-wood-floor-greeter-demo\ui
npm install
npm run dev -- --host 127.0.0.1
```

Open:

- Frontend UI: http://127.0.0.1:5173/

Optional API base override:

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev -- --host 127.0.0.1
```

## Current customer UI

The first screen contains only the virtual consultant, a short explanation, and **开始咨询**.

After the customer starts:

1. The assistant immediately speaks a fixed Chinese greeting and introduction.
2. The customer can press **点击说话** or type a request.
3. Product recommendations appear inside the conversation.
4. **产品对比** opens a focused comparison dialog without exposing engineering controls.
5. **结束并总结** generates a structured consultation summary from the captured customer profile.
6. **重新开始** resets the demo for the next visitor.

The camera is started silently by the frontend so the backend remains ready for the future returning-customer recognition feature. The customer interface does not request or display the MJPEG stream, face boxes, distance, stable-close state, wave state, FPS, backend URL, TTS provider, or model diagnostics.

## Voice interaction

Use Chrome or Edge for the most reliable Web Speech API support.

Recommended test flow:

1. Click **开始咨询**.
2. Confirm that Kokoro plays the Chinese greeting.
3. Click **点击说话** and say one of the sample questions below.
4. Confirm that the response appears in Chinese and is spoken by Kokoro.
5. Open **产品对比**, select two products, and inspect the comparison table.
6. Click **结束并总结** and inspect the structured summary.

Chinese test questions:

```text
家里有宠物，客厅用，现代简约，预算中等，哪种地板好打理？
如果家里装了地暖，应该选 SPC、强化地板还是实木？
潮湿环境或者回南天比较严重，哪种地板更合适？
我喜欢北欧原木风，卧室用，脚感舒服一点怎么选？
```

Important behavior:

- TTS `auto` mode tries local Kokoro first, then OpenAI, then browser SpeechSynthesis.
- TTS playback stops before speech recognition starts, reducing self-listening feedback.
- Voice interaction remains push-to-talk; real-time barge-in is not implemented.
- Camera or vision failure is intentionally hidden from the customer-facing page and does not block button-led consultation.

## More docs

- Local Kokoro setup: `local_tts/README.md`
- OpenAI TTS setup: `backend/OPENAI_TTS_SETUP.md`
