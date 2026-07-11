# Emergency Wood Floor Greeter Demo

Customer-facing wood-floor retail AI assistant demo.

Current product flow:

- customer presses one clear **开始咨询** button
- the assistant checks local, consented face-memory records before creating a new conversation session
- a possible returning-customer match is never trusted automatically; the customer must choose **继续上次咨询 / 开始新的选购项目 / 这不是我**
- the assistant greets the customer, introduces itself, and asks the first needs-discovery question
- Chinese is the default and only customer-facing conversation language for this phase
- browser Web Speech API provides push-to-talk speech recognition
- local Kokoro is the primary TTS provider, with OpenAI and browser SpeechSynthesis fallbacks
- deterministic product recommendation, comparison, customer profile extraction, and session summary remain available
- the OpenCV + MediaPipe camera service runs silently in the backend; no camera image or engineering telemetry is shown to customers
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
- Face identity status: http://127.0.0.1:8000/api/identity/status
- TTS status: http://127.0.0.1:8000/api/tts/status

## Local face identity MVP

The MVP uses OpenCV YuNet for five-landmark face detection and OpenCV SFace for aligned face embeddings. It does not open a second camera. `VisionService` remains the only camera owner and exposes defensive copies of its latest clean frame to the identity service.

Download the two official OpenCV Zoo models once:

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
powershell -ExecutionPolicy Bypass -File .\scripts\download_face_models.ps1
```

The files are stored locally and ignored by Git:

```text
backend/app/data/models/face_detection_yunet_2023mar.onnx
backend/app/data/models/face_recognition_sface_2021dec.onnx
```

Restart the backend and verify:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/identity/status" -Method Get |
  ConvertTo-Json -Depth 20
```

Expected model status:

```text
model.available = true
stores_raw_photos = false
requires_confirmation = true
```

Local biometric and memory data are written to:

```text
backend/app/data/customer_memory.db
```

This database and its WAL files are ignored by Git.

### Privacy and safety behavior

- Face enrollment requires an explicit checkbox and button action from the customer.
- Raw camera frames and aligned face crops are processed in memory and are not stored.
- The database stores normalized float32 face embeddings, customer profiles, compact summaries, and conversation turns.
- Recognition uses multiple frames, a similarity threshold, a top-1/top-2 margin, and voting.
- A match only creates a short-lived candidate token. No history is loaded until the customer confirms it.
- Before confirmation, the UI never displays a customer name or prior consultation content.
- Choosing **这不是我** discards the candidate and starts an anonymous session.
- Every visit gets a fresh `session_id`; `customer_id` and `session_id` are separate.
- **开始新的选购项目** retains only stable household background, not the prior room, budget, style, color, or recommendation.
- This MVP is for low-risk consultation continuity, not payment, access control, or legal identity verification.

Optional threshold settings:

```powershell
$env:FACE_ACCEPT_THRESHOLD="0.45"
$env:FACE_DUPLICATE_THRESHOLD="0.50"
$env:FACE_MARGIN_THRESHOLD="0.04"
$env:FACE_RECOGNITION_SAMPLES="8"
$env:FACE_MIN_VOTES="3"
$env:FACE_ENROLLMENT_SAMPLES="10"
```

The defaults intentionally favor false rejection over loading the wrong customer's history. Tune them only with same-camera, same-lighting local tests.

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

## Face-memory test flow

1. Start the camera, backend, frontend, and both dialogue/TTS services as usual.
2. For the first visit, click **开始咨询**. With no enrolled customers, the app creates a fresh anonymous session.
3. Complete enough conversation to reach **结束并总结**.
4. Click **同意并保存本地记忆**, read the consent, keep the face centered, and start capture.
5. Return to the welcome screen and start another consultation while the same person faces the camera.
6. The UI should show a generic **欢迎回来** confirmation without exposing prior details.
7. Choose **继续上次咨询** to load the previous project, or **开始新的选购项目** to keep only stable household facts.
8. Test a different person. The system should prefer starting a new anonymous session instead of loading the prior history.

## Current customer UI

The first screen contains the virtual consultant, a short explanation, and **开始咨询**.

After the customer starts:

1. The backend performs a local returning-customer candidate check.
2. The customer confirms or rejects any candidate before history is restored.
3. The assistant speaks the appropriate new-customer or returning-customer greeting.
4. The customer can press **点击说话** or type a request.
5. Product recommendations appear inside the conversation.
6. **产品对比** opens a focused comparison dialog without exposing engineering controls.
7. **结束并总结** generates a structured consultation summary and offers optional local face-memory enrollment.
8. **重新开始** ends the current visit and returns to the recognition-aware welcome flow.

## Voice interaction

Use Chrome or Edge for the most reliable Web Speech API support.

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
- Camera or identity failure does not block consultation; the app starts an anonymous session.

## More docs

- Local Kokoro setup: `local_tts/README.md`
- OpenAI TTS setup: `backend/OPENAI_TTS_SETUP.md`
