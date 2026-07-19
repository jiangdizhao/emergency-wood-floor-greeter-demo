# GPT Realtime default voice agent

This document describes the `office` branch voice architecture introduced on 2026-07-19.

## Runtime modes

### Default: GPT Realtime voice

- Audio input: GPT Realtime over WebRTC.
- Turn boundary: manual push-to-talk; automatic VAD is disabled.
- Simple social interaction: handled directly or by a fixed persona response.
- Product facts, recommendations, comparisons, promotions, mutable customer requirements and reasoning: delegated to the existing guarded Terra/Qwen dialogue pipeline.
- Audio output: GPT Realtime remote audio.
- One browser visitor reuses one WebRTC session. A silent WebAudio track is used only to negotiate the initial audio transceiver, then the sender is detached while idle so silence is not continuously uploaded.

### User-selected Kokoro voice

Selecting **Kokoro local voice** changes only the output engine:

- Audio understanding remains GPT Realtime unless the user separately selects Browser ASR.
- Answers still use the same direct/Realtime/Terra routing policy.
- The existing local Kokoro voices and normal Backend/browser fallback remain available.

### Failure fallback

- Realtime audio-output failure: use the existing local Kokoro -> Backend auto -> browser speech chain.
- Realtime input/session failure before listening starts: Browser SpeechRecognition may take over immediately.
- Realtime input/session failure after an active turn has started: the failed turn ends visibly and Browser SpeechRecognition is selected for the next turn; the browser must not unexpectedly begin a new recording after the user already pressed Stop.
- Terra and Qwen remain explicit session-level modes; there is no hidden Terra-to-Qwen or Qwen-to-Terra fallback.

## Authoritative routing

`POST /api/interaction/classify` returns the authoritative route without waiting for Terra.

- Direct routes return a complete ChatResponse-shaped payload immediately.
- A Terra route returns only route metadata, allowing guarded Terra execution to start concurrently with a short Realtime progress cue.

`POST /api/interaction/route` performs the guarded business execution when Terra/Qwen is required.

- `deterministic_direct`: identity, capabilities, greeting, thanks and interaction help.
- `realtime_direct`: safe smalltalk with no product facts and no customer-state mutation.
- `terra`: product/business facts, recommendations, comparisons, promotions, requirements, reasoning and unknown turns.
- `repeat_last`: replay the previous visible answer.
- `stop_speaking`: stop current audio.

Realtime can generate a short safe social answer, but Backend routing decides whether a turn may bypass the guarded business pipeline.

## Important safety rule

An `other` intent must never trigger a product recommendation merely because the profile already contains recommended products. Recommendations refresh only after an explicitly validated `provide_or_modify_needs` turn.

## Persistent push-to-talk session

1. Page startup creates one WebRTC session with a valid silent audio track in the initial SDP.
2. After negotiation, the sender track is detached and the physical microphone remains closed.
3. Pressing the talk button interrupts current Realtime output, opens the microphone and attaches the real microphone track.
4. The runtime waits briefly for RTP stability, then clears the input buffer.
5. Releasing the button commits the buffer and waits for `input_audio_buffer.committed`.
6. The physical microphone is stopped and the sender track is detached again.
7. The same Realtime session is reused for the next turn.

This removes per-turn SDP/session setup while preserving the exhibition requirement that the microphone is active only during push-to-talk and avoiding continuous idle-audio upload.

## Complex-turn latency behavior

For a Terra-routed turn, the frontend starts the guarded Terra request immediately. At the same time, the existing Realtime session says a short fixed cue such as `好的，我正在核对相关信息。`. The cue does not contain a result and is not added to the customer profile. When Terra finishes, its validated answer is spoken by Realtime.

This improves perceived latency without allowing Realtime to invent product facts while Terra is working.

## Local validation

From the repository root:

```powershell
cd .\backend
$env:PYTHONPATH = '.'
python .\scripts\smoke_test_realtime_agent_routing.py
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_realtime_asr.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_realtime_agent_frontend.ps1
```

Frontend:

```powershell
cd ..\ui
npm run build
npm run dev -- --host 127.0.0.1
```

Expected acceptance tests:

1. Ask several product questions, then say `能否再介绍一下自己`.
   - Route log: `deterministic_direct`.
   - No new product recommendation and no profile mutation.
2. Say `见到你很高兴`.
   - Route log: `realtime_direct`.
   - Short natural response, no product facts.
3. Say `我改成浅灰色`.
   - Route log: `terra`.
   - A short progress cue plays while Terra runs.
   - The guarded pipeline updates the confirmed requirement and may refresh recommendations.
4. Say `我喜欢钱会色，不，浅灰色，深浅的浅，灰色的灰`.
   - Final normalized transcript should be `我喜欢浅灰色` or equivalent.
5. Complete five voice turns.
   - Backend should normally show one `/api/realtime/session` creation for the visitor, not one per turn.
6. Press talk while the agent is speaking.
   - Current Realtime output stops without falling back to Kokoro and the microphone starts.
7. Select `Kokoro 本地语音`.
   - Output uses the existing Kokoro path; Realtime remains available for speech understanding.
