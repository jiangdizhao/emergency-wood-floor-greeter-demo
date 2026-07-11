# Parallel dialogue modes: Terra cloud and Qwen local

The backend now exposes two deliberately separate dialogue architectures. A session selects one provider and stays on it until the mode is changed. There is no hidden Terra-to-Qwen or Qwen-to-Terra fallback.

## Shared business core

Both modes use the same local business pipeline:

```text
customer text
→ selected provider parses a SemanticTurn
→ local ValidationGuard
→ local CustomerStateService
→ local deterministic RecommendationService
→ local AnswerPlanService
→ the same selected provider renders the customer answer
→ Kokoro TTS
```

The LLM never writes session files directly and never chooses an arbitrary SKU. Product selection and all persistent customer-state writes remain local and deterministic.

## Mode A: Cloud Intelligence · Terra

- parser: `gpt-5.6-terra`
- answer renderer: `gpt-5.6-terra`
- requires internet and `OPENAI_API_KEY`
- sends only the latest normalized turn, the small current customer profile, the parsing prompt, and the answer plan
- product catalog files and session JSON files remain local
- no automatic Qwen fallback

PowerShell setup for the current terminal:

```powershell
$secureKey = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
Remove-Variable secureKey

$env:OPENAI_DIALOGUE_MODEL="gpt-5.6-terra"
$env:DEFAULT_DIALOGUE_PROVIDER="terra"
```

## Mode B: Private Local AI · Qwen 3.5

- parser: local Ollama `qwen3.5:4b`
- answer renderer: the same local model
- works without internet
- no API-call cost
- customer text and model inference remain on the PC
- lower semantic and language quality is expected on the current laptop
- no automatic Terra fallback

PowerShell setup:

```powershell
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:OLLAMA_DIALOGUE_MODEL="qwen3.5:4b"
$env:DEFAULT_DIALOGUE_PROVIDER="qwen"
```

Recommended Ollama runtime settings:

```powershell
$env:OLLAMA_CONTEXT_LENGTH="4096"
$env:OLLAMA_MAX_LOADED_MODELS="1"
$env:OLLAMA_NUM_PARALLEL="1"
$env:OLLAMA_KEEP_ALIVE="30m"
$env:OLLAMA_NO_CLOUD="1"
```

## Start the backend

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate woodfloor
uvicorn app.main:app --reload --port 8000
```

## Select a provider for a session

```powershell
$body = @{
  session_id = "demo-session-001"
  provider_mode = "terra"   # or qwen
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/session/provider" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body
```

The mode is persisted in:

```text
backend/app/data/sessions/<session-id>.runtime.json
```

Resetting the customer profile does not change the selected provider.

## Status endpoint

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/llm/status?session_id=demo-session-001" `
  -Method Get | ConvertTo-Json -Depth 20
```

The response shows the active mode, configured model names, provider availability, and confirms that cross-provider fallback is disabled. It never returns API keys or prompts.

## Chat endpoint

`provider_mode` is optional. When supplied it updates the session selection before handling the turn.

```json
{
  "session_id": "demo-session-001",
  "provider_mode": "qwen",
  "response_language": "zh",
  "text": "客厅用，家里有两只猫，预算中等，耐磨和好清洁最重要，请推荐一下。"
}
```

The response additionally reports:

```json
{
  "provider_mode": "qwen",
  "provider_label": "Private Local AI · Qwen 3.5",
  "llm_degraded": false,
  "needs_clarification": false
}
```

## Failure policy

Terra mode:

```text
Terra parse fails
→ no state mutation
→ return a cloud-service-unavailable message

Terra answer rendering fails after a valid parse
→ use the existing deterministic ChatService template
→ remain in Terra mode
```

Qwen mode:

```text
Qwen parse is incomplete or rejected by ValidationGuard
→ no state mutation
→ ask a clarification question using Qwen/local deterministic text

Ollama is unavailable
→ no state mutation
→ return a local-model-unavailable message

Qwen answer rendering fails after a valid parse
→ use the existing deterministic ChatService template
→ remain in Qwen mode
```

## Smoke tests

Qwen mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_parallel_llm.ps1 -ProviderMode qwen
```

Terra mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_parallel_llm.ps1 -ProviderMode terra
```

The smoke script tests provider selection, a multi-condition recommendation, and a negation/correction turn.

## Important implementation boundaries

- `backend/app/llm/providers.py`: provider-specific OpenAI/Ollama calls
- `backend/app/services/validation_guard.py`: shared safety and completeness checks
- `backend/app/services/customer_state_service.py`: the only semantic-action-to-profile writer
- `backend/app/services/recommendation_service.py`: deterministic SKU scoring and filtering
- `backend/app/services/answer_plan_service.py`: approved product facts passed to the renderer
- `backend/app/services/dialogue_orchestrator.py`: shared pipeline and same-provider enforcement
