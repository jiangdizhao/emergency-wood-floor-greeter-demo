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

const PROVIDER_STORAGE_KEY = 'woodfloor_asr_provider'
const REALTIME_PROVIDER = 'gpt-realtime-2'

function runtime(): RealtimeAgentRuntime {
  return getRealtimeAgentRuntime()
}

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
    void runtime()
      .beginCapture()
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
    void runtime()
      .endCapture()
      .then((rawTranscript) => {
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
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error)
        const noSpeech = /too short|没有收到|unintelligible|录音时间太短/i.test(message)
        this.onerror?.({ error: noSpeech ? 'no-speech' : 'network', message })
      })
      .finally(() => this.emitEnd())
  }

  abort(): void {
    if (this.ended) return
    this.started = false
    void runtime()
      .abortCapture()
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
  await runtime().prewarm()
}

export function resetRealtimeRecognition(): void {
  const agent = runtime()
  void agent.abortCapture().catch(() => undefined)
  void agent.stopOutput().catch(() => undefined)
}

;(window as Window & { __woodfloorRealtimeSpeechReset?: () => void }).__woodfloorRealtimeSpeechReset =
  resetRealtimeRecognition
