# Emergency Wood Floor Greeter Demo

2-day demo for a wood-floor retail AI greeter:

- simulated customer session state machine
- product catalog API
- voice/wave greeting trigger API
- deterministic product recommendation
- simulated customer profile / lead save

## Backend quick start

```powershell
cd backend
conda activate woodfloor
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open:

- API root: http://127.0.0.1:8000/
- Health: http://127.0.0.1:8000/api/health
- Docs: http://127.0.0.1:8000/docs

## Windows PowerShell notes

In Windows PowerShell, `curl` is often an alias for `Invoke-WebRequest`, not real curl. Therefore Linux-style flags such as `-H` and `-d` may fail. Use either `Invoke-RestMethod` or `curl.exe`.

To reduce garbled Chinese output in the terminal, run this first:

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

## Smoke tests with Invoke-RestMethod

Health check:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -Method Get
```

Product list:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/products" -Method Get | ConvertTo-Json -Depth 10
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

This commit makes the backend runnable. `/api/vision/status` is currently simulated so the backend does not depend on camera drivers during startup. The next step is to attach the real OpenCV + MediaPipe vision service.
