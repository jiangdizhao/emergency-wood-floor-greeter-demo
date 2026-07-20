# GPT Realtime voice agent — office branch

This document describes the `office` branch voice architecture. The `main` branch keeps its retail-greeter behavior; office-specific changes must not be applied to `main`.

## Office branch differences

- Proactive narration is disabled completely.
- The proactive narration dock, toggle, timers, scripts and TTS adapter are absent from the office frontend.
- The user selects exactly one voice-output owner.
- Automatic switching between GPT Realtime, Kokoro, OpenAI TTS and browser speech synthesis is disabled.
- Provider failure leaves the answer text visible and reports an error; it never starts a second voice.

## Voice-output modes

### GPT Realtime 2 — default

- Audio input: GPT Realtime over WebRTC.
- Simple safe social turns: GPT Realtime generates and speaks the answer.
- Deterministic persona responses and Terra/Qwen business answers: GPT Realtime reads the final validated text.
- `/api/tts` is not used for audible output in this mode.
- Failure does not invoke Kokoro, OpenAI TTS or browser speech synthesis.

### Kokoro local voice

- Speech understanding can still use GPT Realtime or Browser ASR.
- Simple Realtime turns are generated as text only.
- Final output uses `/api/tts` with `provider=local` only.
- If Kokoro is unavailable, the answer remains visible and no other voice starts.

### OpenAI TTS

- Speech understanding can still use GPT Realtime or Browser ASR.
- Simple Realtime turns are generated as text only.
- Final output uses `/api/tts` with `provider=openai` only.
- If OpenAI TTS is unavailable, the answer remains visible and no other voice starts.

`auto` is not used by the office frontend. Browser `speechSynthesis` is explicitly blocked as an output fallback.

## Single playback owner

`ui/src/voiceOutputManager.ts` is the final frontend gate for every `/api/tts` request.

It provides:

- the three explicit user-selectable modes;
- one active HTML media element at a time;
- cancellation of existing Realtime and HTML audio when the user changes modes;
- duplicate-text suppression for legacy React retry attempts;
- explicit `local` or `openai` provider rewriting;
- valid silent acknowledgements after Realtime has already spoken, or after a provider failure, so the old React retry chain cannot launch a second voice;
- visible provider status beside the voice selector;
- no browser TTS fallback.

## Authoritative routing

`POST /api/interaction/classify` returns the authoritative route without waiting for Terra.

`POST /api/interaction/route` performs guarded Terra/Qwen business execution.

- `deterministic_direct`: identity, capabilities, greeting, thanks and interaction help.
- `realtime_direct`: safe smalltalk with no product facts and no customer-state mutation.
- `terra`: product facts, recommendations, comparisons, promotions, requirements, reasoning and unknown turns.
- `repeat_last`: repeat the previous visible answer through the selected voice provider.
- `stop_speaking`: stop all current voice output.

For `realtime_direct`:

- Realtime output mode uses Realtime audio and marks that text as already played.
- Kokoro or OpenAI TTS mode requests a text-only Realtime answer, then the selected provider reads it.

Terra processing uses the visual processing indicator only. There is no spoken Realtime progress cue because that would violate the selected provider's ownership.

## Persistent push-to-talk session

1. Page startup creates one WebRTC session with a valid silent audio track in the initial SDP.
2. After negotiation, the sender track is detached and the physical microphone remains closed.
3. Pressing the talk button stops current output, opens the microphone and attaches the real microphone track.
4. The runtime waits briefly for RTP stability and clears the input buffer.
5. Releasing the button commits the buffer and waits for `input_audio_buffer.committed`.
6. The physical microphone is stopped and the sender track is detached again.
7. The same Realtime session is reused for the next turn.

## Long GPT Realtime speech

`ui/src/realtimeLongAudioTimeoutPatch.ts` replaces the old fixed 30-second total response timeout for audio turns.

- Text-only Realtime operations keep a 30-second timeout.
- Audio must begin within 15 seconds.
- Once `output_audio_buffer.started` is received, the start timer is removed.
- The completion safety window is estimated from the amount of Chinese text and English words in the reading instruction.
- The completion window is never shorter than 90 seconds and is capped at 360 seconds.
- Normal completion still requires both `response.done` and `output_audio_buffer.stopped`.
- User interruption, stop commands and voice-mode changes can still cancel playback immediately.

This prevents a normal long welcome message or product explanation from being cancelled after exactly 30 seconds, while retaining a bounded watchdog for genuinely stuck audio.

## Local validation

```powershell
cd .\backend
$env:PYTHONPATH = '.'
python .\scripts\smoke_test_realtime_agent_routing.py
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_realtime_asr.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_test_realtime_agent_frontend.ps1
```

```powershell
cd ..\ui
npm run build
npm run dev -- --host 127.0.0.1
```

## Acceptance tests

1. Wait two minutes on the consultation page.
   - No proactive narration dock, icon, text, timer or TTS request appears.
2. Select GPT Realtime 2 and ask a question.
   - One Realtime voice speaks once.
   - No `/api/tts` audible provider and no browser voice starts.
3. Read a Chinese answer of at least 150 characters.
   - Audio begins normally and continues beyond 30 seconds when needed.
   - The UI does not report a timeout while speech is still progressing.
   - The full final sentence is spoken before playback completes.
4. Select Kokoro and ask a question.
   - Only `provider=local` is requested.
   - Realtime audio and OpenAI TTS remain silent.
5. Stop Kokoro and repeat the test.
   - The answer text remains visible.
   - No Realtime, OpenAI or browser voice starts.
6. Select OpenAI TTS and ask a question.
   - Only `provider=openai` is requested.
7. Change voice mode during a long answer.
   - Existing audio stops immediately.
   - No two speakers overlap.
8. Ask several product questions and then say `能否再介绍一下自己`.
   - Route: `deterministic_direct`.
   - No product recommendation leaks into the identity response.
9. Complete five voice turns.
   - The browser normally creates one `/api/realtime/session`, not one per turn.
