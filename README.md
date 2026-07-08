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

## Smoke tests

```powershell
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/products
```

Simulate customer close:

```powershell
curl -X POST http://127.0.0.1:8000/api/demo/event `
  -H "Content-Type: application/json" `
  -d '{"event":"person_close"}'
```

Simulate voice greeting:

```powershell
curl -X POST http://127.0.0.1:8000/api/greeting/voice `
  -H "Content-Type: application/json" `
  -d '{"text":"你好"}'
```

Ask a product question:

```powershell
curl -X POST http://127.0.0.1:8000/api/chat `
  -H "Content-Type: application/json" `
  -d '{"text":"家里有宠物，客厅用，现代简约，预算中等，哪种地板好打理？"}'
```

Compare products:

```powershell
curl -X POST http://127.0.0.1:8000/api/products/compare `
  -H "Content-Type: application/json" `
  -d '{"product_ids":["WF-SPC-001","WF-WOOD-002"]}'
```

## Current implementation status

This commit makes the backend runnable. `/api/vision/status` is currently simulated so the backend does not depend on camera drivers during startup. The next step is to attach the real OpenCV + MediaPipe vision service.
