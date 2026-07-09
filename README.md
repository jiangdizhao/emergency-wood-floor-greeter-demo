# Emergency Wood Floor Greeter Demo

2-day demo for a wood-floor retail AI greeter:

- simulated customer session state machine
- product catalog API
- voice/wave greeting trigger API
- deterministic bilingual product recommendation
- simulated customer profile / lead save
- real OpenCV + MediaPipe vision service for face-close and wave greeting detection
- fullscreen React retail demo UI
- browser Web Speech API speech recognition
- TTS providers: local Kokoro, OpenAI, and browser SpeechSynthesis fallback
- language-choice prompt after greeting, with English as default

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

`requirements.txt` records these user-verified versions. If your local environment already has them installed and working, do not run `--force-reinstall`.

Open:

- API root: http://127.0.0.1:8000/
- Health: http://127.0.0.1:8000/api/health
- Docs: http://127.0.0.1:8000/docs
- Vision stream: http://127.0.0.1:8000/api/vision/stream
- Vision status: http://127.0.0.1:8000/api/vision/status
- TTS status: http://127.0.0.1:8000/api/tts/status

## Local Kokoro TTS quick start

Run Kokoro in the separate conda environment you already tested:

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
powershell -ExecutionPolicy Bypass -File .\start_kokoro_tts.ps1
```

If the environment does not have FastAPI/Uvicorn yet:

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
python -m pip install -r requirements.txt
```

Smoke test:

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1
```

Then start the main backend and point it to the local Kokoro service:

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate woodfloor
$env:LOCAL_TTS_URL="http://127.0.0.1:8010/tts"
$env:LOCAL_TTS_HEALTH_URL="http://127.0.0.1:8010/health"
uvicorn app.main:app --reload --port 8000
```

Check main backend TTS status:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/tts/status" -Method Get | ConvertTo-Json -Depth 10
```

## OpenAI TTS fallback

OpenAI TTS is still supported as a fallback. Set the key only in your local PowerShell session before starting backend:

```powershell
$env:OPENAI_API_KEY="sk-your-real-key-here"
$env:OPENAI_TTS_MODEL="gpt-4o-mini-tts"
$env:OPENAI_TTS_VOICE="marin"
```

Do not commit a real key. `.env` files are ignored.

## Frontend quick start

Start the backend first. Then open a second terminal:

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

Current UI features:

1. MJPEG camera stream panel from `/api/vision/stream`.
2. Live status cards for person, distance, stable close, wave, FPS and state.
3. Demo fallback buttons: Start Vision, Stop Vision, Simulate Close, Simulate Wave, Simulate Voice Hi, Reset Session.
4. Text-based AI guide chat via `/api/chat`.
5. Browser speech recognition for Chinese Mandarin and English.
6. TTS provider selector: `Local Kokoro → OpenAI → Browser`, `Local Kokoro only`, `OpenAI only`, or `Browser only`.
7. Language-choice prompt after greeting: English by default; say `Chinese` or `中文` to use Chinese.
8. Product cards, recommendation highlighting, comparison, and customer need profile.

## Voice interaction

Use Chrome or Edge for the most reliable Web Speech API support.

Recommended flow:

1. Start local Kokoro TTS service, main backend, and frontend.
2. Click `Start Vision`.
3. Move close to the camera until the state becomes `顾客已靠近，等待问候`.
4. Say `hello` or wave while close to the camera.
5. The AI greeter asks: `Which language would you like to use, Chinese or English? English is the default.`
6. Say `Chinese` or type/click `中文` to use Chinese. Otherwise, the conversation continues in English.
7. After language selection, the AI plays the welcome message in the selected language.
8. Click `Start Listening` again and ask product questions.

Important behavior:

- Auto TTS mode tries local Kokoro first, then OpenAI, then browser fallback.
- Voice greeting requires the customer to be close to the camera, same as wave greeting.
- TTS playback is stopped before listening starts to avoid the system hearing its own answer.
- This is push-to-talk voice interaction, not real-time barge-in interruption.
- If local Kokoro or OpenAI TTS fails, use browser fallback.

English test questions:

```text
I have pets and want flooring for a modern living room. Which floor is easy to clean?
Which option is better for underfloor heating, SPC, laminate, or engineered wood?
What is the difference between SPC flooring and engineered wood?
```

Chinese test questions:

```text
家里有宠物，客厅用，现代简约，预算中等，哪种地板好打理？
如果家里装了地暖，应该选 SPC、强化地板还是实木？
潮湿环境或者回南天比较严重，哪种地板更合适？
```

## More docs

- Local Kokoro setup: `local_tts/README.md`
- OpenAI TTS setup: `backend/OPENAI_TTS_SETUP.md`
