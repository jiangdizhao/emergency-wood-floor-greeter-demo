# Emergency Wood Floor Greeter Demo

2-day demo for a wood-floor retail AI greeter:

- simulated customer session state machine
- product catalog API
- voice/wave greeting trigger API
- deterministic product recommendation
- simulated customer profile / lead save
- real OpenCV + MediaPipe vision service for face-close and wave greeting detection

## Backend quick start

```powershell
cd backend
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
- UTF-8 JSON debug: http://127.0.0.1:8000/api/debug/encoding
- UTF-8 plain-text debug: http://127.0.0.1:8000/api/debug/plain-utf8

## Vision service

The backend owns the camera. The frontend should display the MJPEG stream from `/api/vision/stream`; it should not open the camera directly.

Endpoints:

- `POST /api/vision/start`
- `POST /api/vision/stop`
- `GET /api/vision/status`
- `GET /api/vision/stream`

Vision smoke test:

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_vision.ps1
```

Expected flow:

1. Start the vision service.
2. Open http://127.0.0.1:8000/api/vision/stream in a browser.
3. Move close to the camera; status should become `PERSON_CLOSE_WAITING_GREETING`.
4. Wave left/right; status should become `GREETING_RECEIVED`.

Manual vision commands:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/vision/start" -Method Post
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/vision/status" -Method Get | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/vision/stop" -Method Post
```

## Windows PowerShell notes

In Windows PowerShell, `curl` is often an alias for `Invoke-WebRequest`, not real curl. Therefore Linux-style flags such as `-H` and `-d` may fail. Use either `Invoke-RestMethod`, the provided smoke test script, or `curl.exe`.

To reduce garbled Chinese output in the terminal, run this first:

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

## Recommended backend smoke test

Start the backend in one terminal, then run this in another terminal:

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_backend.ps1
```

This script uses raw UTF-8 decoding for the debug endpoints and avoids the Windows PowerShell `curl` alias problem.

## Manual smoke tests with Invoke-RestMethod

Health check:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Method Get
```

Encoding debug:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/debug/encoding" -Method Get | ConvertTo-Json -Depth 10
```

Product list:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/products" -Method Get | ConvertTo-Json -Depth 10
```

If the terminal still shows mojibake, use explicit raw-byte UTF-8 decoding:

```powershell
$resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/products" -UseBasicParsing
$reader = New-Object System.IO.StreamReader($resp.RawContentStream, [System.Text.Encoding]::UTF8)
$text = $reader.ReadToEnd()
$text
```

Simulate customer close:

```powershell
$body = @{ event = "person_close" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/demo/event" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

Simulate voice greeting:

```powershell
$body = @{ text = "你好" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/greeting/voice" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

Ask a product question:

```powershell
$body = @{ text = "家里有宠物，客厅用，现代简约，预算中等，哪种地板好打理？" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body | ConvertTo-Json -Depth 10
```

Compare products:

```powershell
$body = @{ product_ids = @("WF-SPC-001", "WF-WOOD-002") } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/products/compare" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body | ConvertTo-Json -Depth 10
```

## Smoke tests with real curl.exe

```powershell
curl.exe http://127.0.0.1:8000/api/health
curl.exe http://127.0.0.1:8000/api/products

curl.exe -X POST "http://127.0.0.1:8000/api/demo/event" `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-raw "{\"event\":\"person_close\"}"

curl.exe -X POST "http://127.0.0.1:8000/api/greeting/voice" `
  -H "Content-Type: application/json; charset=utf-8" `
  --data-raw "{\"text\":\"你好\"}"
```

## Current implementation status

The backend is runnable and includes a real OpenCV + MediaPipe vision service. The service detects face-close status and hand-wave greetings, then updates the backend state machine. The next step is to build the frontend retail demo UI.
