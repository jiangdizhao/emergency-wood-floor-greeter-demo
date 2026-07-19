import { getRealtimeAgentRuntime, type RealtimeAgentRuntime } from './realtimeAgentRuntime'

export type RecognitionAlternative = { transcript: string; confidence?: number }

export type RecognitionResult = {
  isFinal?: boolean
  length: number
  [index: number]: RecognitionAlternative
}

export type RecognitionEvent = {
  results: {
    length: number
    [index: number]: RecognitionResult
  }
}

export type RecognitionErrorEvent = { error: string; message?: string }

export type RecognitionLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onstart: (() => void) | null
  onend: (() => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onresult: ((event: RecognitionEvent) => void) | null
}

type RuntimeInternals = RealtimeAgentRuntime & {
  sender?: RTCRtpSender | null
}

const PROVIDER_STORAGE_KEY = 'woodfloor_asr_provider'
const REALTIME_PROVIDER = 'gpt-realtime-2'

function runtime(): RealtimeAgentRuntime {
  return getRealtimeAgentRuntime()
}

async function detachIdleInputTrack(agent: RealtimeAgentRuntime): Promise<void> {
  // PersistentRealtimeAgent uses a normal TypeScript private property, which is a
  // regular JS property after compilation. Detaching after the initial SDP keeps
  // the negotiated audio transceiver reusable without continuously sending silence.
  const sender = (agent as RuntimeInternals).sender
  if (sender) await sender.replaceTrack(null)
}

window.addEventListener('woodfloor:realtime-connected', () => {
  void detachIdleInputTrack(runtime()).catch((error) => {
    console.warn('Could not detach the idle Realtime input track:', error)
  })
})

export function realtimeAsrSelected(): boolean {
  const configured = localStorage.getItem(PROVIDER_STORAGE_KEY)
  if (!configured) {
    localStorage.setItem(PROVIDER_STORAGE_KEY, REALTIME_PROVIDER)
    return true
  }
  return configured === REALTIME_PROVIDER
}

function normalizeTranscript(value: string): string {
  let text = String(value || '').trim()
  text = text.replace(/^```(?:text|json)?\s*/i, '').replace(/\s*```$/, '').trim()
  text = text.replace(/^(?:transcript|normalized utterance|最终文本|规范文本|识别结果)\s*[:：]\s*/i, '')
  if (
    (text.startsWith('"') && text.endsWith('"')) ||
    (text.startsWith('“') && text.endsWith('”')) ||
    (text.startsWith("'") && text.endsWith("'"))
  ) {
    text = text.slice(1, -1).trim()
  }
  return text.replace(/\s+/g, ' ').trim()
}

function recognitionEvent(text: string): RecognitionEvent {
  const result = [{ transcript: text, confidence: 1 }] as unknown as RecognitionResult
  result.isFinal = true
  return { results: [result] as unknown as RecognitionEvent['results'] }
}

export class RealtimeRecognition implements RecognitionLike {
  lang = 'zh-CN'
  continuous = true
  interimResults = true
  maxAlternatives = 1
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: ((event: RecognitionErrorEvent) => void) | null = null
  onresult: ((event: RecognitionEvent) => void) | null = null

  private started = false
  private ended = false
  private stopRequested = false

  start(): void {
    this.started = false
    this.ended = false
    this.stopRequested = false
    const agent = runtime()
    // Interrupt outside the runtime operation queue. This releases an active
    // Realtime audio response before the microphone-start operation is enqueued.
    void agent
      .stopOutput()
      .catch(() => undefined)
      .then(() => agent.beginCapture())
      .then(() => {
        if (this.ended) return
        this.started = true
        this.onstart?.()
        if (this.stopRequested) this.stop()
      })
      .catch((error: unknown) => {
        this.emitError('network', error)
        this.emitEnd()
      })
  }

  stop(): void {
    this.stopRequested = true
    if (!this.started || this.ended) return
    this.started = false
    const agent = runtime()
    void agent
      .endCapture()
      .then(async (rawTranscript) => {
        await detachIdleInputTrack(agent)
        const transcript = normalizeTranscript(rawTranscript)
        if (!transcript || transcript === '__UNCLEAR__') {
          this.onerror?.({
            error: 'no-speech',
            message: '周围声音较大或语音仍有歧义，请靠近麦克风后再说一次。',
          })
          return
        }
        this.onresult?.(recognitionEvent(transcript))
      })
      .catch(async (error: unknown) => {
        await detachIdleInputTrack(agent).catch(() => undefined)
        const message = error instanceof Error ? error.message : String(error)
        const noSpeech = /too short|没有收到|unintelligible|录音时间太短/i.test(message)
        this.onerror?.({ error: noSpeech ? 'no-speech' : 'network', message })
      })
      .finally(() => this.emitEnd())
  }

  abort(): void {
    if (this.ended) return
    this.started = false
    const agent = runtime()
    void agent
      .abortCapture()
      .catch(() => undefined)
      .then(() => detachIdleInputTrack(agent))
      .catch(() => undefined)
      .finally(() => this.emitEnd())
  }

  private emitError(error: string, value: unknown): void {
    const message = value instanceof Error ? value.message : String(value)
    this.onerror?.({ error, message })
  }

  private emitEnd(): void {
    if (this.ended) return
    this.ended = true
    this.started = false
    this.onend?.()
  }
}

export async function prewarmRealtimeRecognition(): Promise<void> {
  const agent = runtime()
  await agent.prewarm()
  await detachIdleInputTrack(agent)
}

export function resetRealtimeRecognition(): void {
  const agent = runtime()
  void agent
    .abortCapture()
    .catch(() => undefined)
    .then(() => detachIdleInputTrack(agent))
    .catch(() => undefined)
  void agent.stopOutput().catch(() => undefined)
}

;(window as Window & { __woodfloorRealtimeSpeechReset?: () => void }).__woodfloorRealtimeSpeechReset =
  resetRealtimeRecognition
