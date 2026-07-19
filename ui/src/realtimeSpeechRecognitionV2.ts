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

type ServerEvent = {
  type?: string
  delta?: string
  text?: string
  response?: {
    status?: string
    status_details?: { error?: { message?: string } }
    metadata?: Record<string, unknown>
    output?: Array<{ content?: Array<{ text?: string; transcript?: string }> }>
  }
  error?: { message?: string; code?: string }
}

type Sink = {
  requestId: string
  onStarted: () => void
  onTranscript: (text: string) => void
  onUnclear: (message: string) => void
  onFailure: (message: string) => void
  onEnded: () => void
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000'
const PROVIDER_STORAGE_KEY = 'woodfloor_asr_provider'
const REALTIME_PROVIDER = 'gpt-realtime-2'
const MIN_CAPTURE_MS = 250
const DATA_CHANNEL_TIMEOUT_MS = 12_000
const COMMIT_TIMEOUT_MS = 4_000
const RESPONSE_TIMEOUT_MS = 30_000
const RTP_DRAIN_MS = 200

function selectedLanguage(): 'zh' | 'en' {
  const configured = (window as Window & { __WOODFLOOR_LANGUAGE__?: string }).__WOODFLOOR_LANGUAGE__
  return configured === 'en' || localStorage.getItem('woodfloor_ui_language') === 'en' ? 'en' : 'zh'
}

function currentSessionId(): string {
  const key = 'woodfloor_realtime_browser_session_id'
  const existing = sessionStorage.getItem(key)
  if (existing) return existing
  const created = `browser-${crypto.randomUUID()}`
  sessionStorage.setItem(key, created)
  return created
}

export function realtimeAsrSelected(): boolean {
  return localStorage.getItem(PROVIDER_STORAGE_KEY) === REALTIME_PROVIDER
}

function recentContext(): string {
  const rows = Array.from(document.querySelectorAll<HTMLElement>('.chat-log .message-row')).slice(-8)
  const lines = rows.map((row) => {
    const role = row.classList.contains('customer') ? 'User' : 'Assistant'
    let text = row.querySelector('p')?.textContent?.replace(/\s+/g, ' ').trim() ?? ''
    text = text
      .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[email redacted]')
      .replace(/(?:\+?\d[\d\s()-]{7,}\d)/g, '[phone redacted]')
    return text ? `${role}: ${text}` : ''
  })
  return lines.filter(Boolean).join('\n') || '(no prior visible conversation)'
}

function instructions(): string {
  const language = selectedLanguage()
  const terms =
    language === 'en'
      ? 'light grey, grey, natural oak, dark walnut, cream white, SPC, engineered wood, laminate, waterproof, wear resistance, underfloor heating, pets, living room, bedroom, whole home'
      : '浅灰色、浅灰、灰色、深灰色、原木色、深胡桃色、奶油白、SPC、多层实木、强化地板、防水、耐磨、地暖、宠物、客厅、卧室、全屋'
  return `
You are a speech-understanding layer, not a conversational assistant.
Return only the user's final intended utterance as plain text. Do not answer the user.
Language: ${language === 'en' ? 'English' : 'Chinese Mandarin'}.
Recent conversation:
${recentContext()}
Relevant vocabulary:
${terms}
Later explicit corrections override earlier uncertain words.
Chinese signals such as “不”, “不是”, “不对”, “我是说”, “应该是” and character explanations are authoritative.
Example: “我喜欢钱会色，不，浅灰色，深浅的浅，灰色的灰” becomes “我喜欢浅灰色”.
Keep requirements the user did not retract. Never invent a preference.
If the audio is genuinely unintelligible or equally ambiguous, output exactly __UNCLEAR__.
Otherwise output only normalized plain text without labels, JSON, Markdown or quotation marks.
`.trim()
}

function normalizeOutput(value: string): string {
  let text = value.trim()
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

function responseText(event: ServerEvent): string {
  if (event.text?.trim()) return event.text.trim()
  const parts: string[] = []
  for (const output of event.response?.output ?? []) {
    for (const content of output.content ?? []) {
      if (content.text?.trim()) parts.push(content.text.trim())
      else if (content.transcript?.trim()) parts.push(content.transcript.trim())
    }
  }
  return parts.join(' ').trim()
}

function recognitionEvent(text: string): RecognitionEvent {
  const result = [{ transcript: text, confidence: 1 }] as unknown as RecognitionResult
  result.isFinal = true
  return { results: [result] as unknown as RecognitionEvent['results'] }
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

class RealtimeClient {
  private pc: RTCPeerConnection | null = null
  private dc: RTCDataChannel | null = null
  private stream: MediaStream | null = null
  private track: MediaStreamTrack | null = null
  private sink: Sink | null = null
  private captureStartedAt = 0
  private output = ''
  private commitPending = false
  private responsePending = false
  private commitTimer: number | null = null
  private responseTimer: number | null = null

  async begin(sink: Sink): Promise<void> {
    await this.shutdown()
    this.sink = sink
    this.output = ''
    this.commitPending = false
    this.responsePending = false

    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      })
      this.track = this.stream.getAudioTracks()[0] ?? null
      if (!this.track) throw new Error('No microphone audio track is available.')

      // The real microphone track must be in the initial SDP offer. Adding it only
      // after negotiation can leave OpenAI's input buffer at 0 ms on some browsers.
      await this.connectWithTrack(this.track, this.stream)
      if (this.sink !== sink) return
      this.send({ type: 'input_audio_buffer.clear' })
      this.captureStartedAt = performance.now()
      sink.onStarted()
    } catch (error) {
      await this.shutdown()
      if (this.sink === sink) this.sink = null
      throw error
    }
  }

  async end(sink: Sink): Promise<void> {
    if (this.sink !== sink) return
    const duration = performance.now() - this.captureStartedAt
    if (!this.captureStartedAt || duration < MIN_CAPTURE_MS) {
      await this.finish(sink, () => sink.onUnclear('录音时间太短，请按住按钮并完整说完。'))
      return
    }

    // Keep the microphone attached until final RTP packets have reached the server.
    await wait(RTP_DRAIN_MS)
    if (this.sink !== sink) return

    this.commitPending = true
    this.send({ type: 'input_audio_buffer.commit' })
    this.commitTimer = window.setTimeout(() => {
      if (this.sink !== sink || !this.commitPending) return
      void this.finish(sink, () => sink.onFailure('GPT Realtime 未确认收到音频，请重试。'))
    }, COMMIT_TIMEOUT_MS)
  }

  abort(sink: Sink): void {
    if (this.sink !== sink) return
    if (this.responsePending) this.send({ type: 'response.cancel' })
    this.send({ type: 'input_audio_buffer.clear' })
    void this.finish(sink)
  }

  async prewarm(): Promise<void> {
    if (!window.RTCPeerConnection) throw new Error('This browser does not support WebRTC.')
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('This browser cannot access a microphone.')
    const response = await fetch(`${API_BASE_URL}/api/realtime/status`, {
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
    const status = (await response.json()) as { configured?: boolean; enabled?: boolean }
    if (!status.configured || !status.enabled) throw new Error('GPT Realtime is not configured.')
  }

  reset(): void {
    const sink = this.sink
    if (this.responsePending) this.send({ type: 'response.cancel' })
    this.send({ type: 'input_audio_buffer.clear' })
    this.sink = null
    void this.shutdown()
    if (sink) {
      sink.onFailure('GPT Realtime 连接已重置。')
      sink.onEnded()
    }
  }

  private async connectWithTrack(track: MediaStreamTrack, stream: MediaStream): Promise<void> {
    const pc = new RTCPeerConnection()
    const dc = pc.createDataChannel('oai-events')
    this.pc = pc
    this.dc = dc
    pc.addTrack(track, stream)

    dc.addEventListener('message', (event) => this.onServerEvent(event))
    pc.addEventListener('connectionstatechange', () => {
      if (!['failed', 'disconnected'].includes(pc.connectionState)) return
      const sink = this.sink
      if (sink) void this.finish(sink, () => sink.onFailure('GPT Realtime WebRTC 连接已断开。'))
    })

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const sdp = pc.localDescription?.sdp ?? offer.sdp
    if (!sdp) throw new Error('Could not create WebRTC SDP offer.')

    const response = await fetch(
      `${API_BASE_URL}/api/realtime/session?session_id=${encodeURIComponent(currentSessionId())}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: sdp,
      },
    )
    if (!response.ok) {
      const detail = await response.text().catch(() => '')
      throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ''}`)
    }
    await pc.setRemoteDescription({ type: 'answer', sdp: await response.text() })
    await this.waitForDataChannel(dc)

    this.send({
      type: 'session.update',
      session: {
        type: 'realtime',
        output_modalities: ['text'],
        audio: { input: { turn_detection: null } },
      },
    })
  }

  private onServerEvent(message: MessageEvent<string>): void {
    let event: ServerEvent
    try {
      event = JSON.parse(message.data) as ServerEvent
    } catch {
      return
    }

    if (event.type === 'response.output_text.delta' && typeof event.delta === 'string') {
      this.output += event.delta
      return
    }
    if (event.type === 'response.output_text.done' && typeof event.text === 'string') {
      this.output = event.text
      return
    }

    if (event.type === 'input_audio_buffer.committed') {
      const sink = this.sink
      if (!sink || !this.commitPending) return
      this.commitPending = false
      this.clearCommitTimer()
      void this.stopMicrophone()
      this.responsePending = true
      this.send({
        type: 'response.create',
        response: {
          output_modalities: ['text'],
          metadata: { purpose: 'speech_understanding', request_id: sink.requestId },
          instructions: instructions(),
        },
      })
      this.responseTimer = window.setTimeout(() => {
        if (this.sink !== sink) return
        this.send({ type: 'response.cancel' })
        void this.finish(sink, () => sink.onFailure('GPT Realtime 语音理解超时，请重试。'))
      }, RESPONSE_TIMEOUT_MS)
      return
    }

    if (event.type === 'error') {
      if (['response_cancel_not_active', 'input_audio_buffer_clear_empty'].includes(event.error?.code ?? '')) return
      const sink = this.sink
      if (!sink) return
      const messageText = event.error?.message || 'GPT Realtime returned an unknown error.'
      const empty = /buffer too small|0\.00ms/i.test(messageText)
      void this.finish(sink, () => {
        if (empty) sink.onUnclear('没有收到语音，请看到“正在聆听”后再完整说话。')
        else sink.onFailure(messageText)
      })
      return
    }

    if (event.type !== 'response.done') return
    const sink = this.sink
    if (!sink) return
    const requestId = event.response?.metadata?.request_id
    if (typeof requestId === 'string' && requestId !== sink.requestId) return
    const normalized = normalizeOutput(this.output || responseText(event))
    const failed = event.response?.status === 'failed'
    this.output = ''

    void this.finish(sink, () => {
      if (failed) sink.onFailure(event.response?.status_details?.error?.message || 'GPT Realtime response failed.')
      else if (!normalized || normalized === '__UNCLEAR__') {
        sink.onUnclear('周围声音较大或语音仍有歧义，请靠近麦克风后再说一次。')
      } else sink.onTranscript(normalized)
    })
  }

  private waitForDataChannel(channel: RTCDataChannel): Promise<void> {
    if (channel.readyState === 'open') return Promise.resolve()
    return new Promise((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        cleanup()
        reject(new Error('Timed out while opening GPT Realtime data channel.'))
      }, DATA_CHANNEL_TIMEOUT_MS)
      const cleanup = () => {
        clearTimeout(timeout)
        channel.removeEventListener('open', onOpen)
        channel.removeEventListener('error', onError)
      }
      const onOpen = () => {
        cleanup()
        resolve()
      }
      const onError = () => {
        cleanup()
        reject(new Error('Could not open GPT Realtime data channel.'))
      }
      channel.addEventListener('open', onOpen)
      channel.addEventListener('error', onError)
    })
  }

  private send(event: Record<string, unknown>): void {
    if (this.dc?.readyState === 'open') this.dc.send(JSON.stringify(event))
  }

  private async finish(sink: Sink, notify?: () => void): Promise<void> {
    if (this.sink !== sink) return
    this.sink = null
    this.commitPending = false
    this.responsePending = false
    await this.shutdown()
    notify?.()
    sink.onEnded()
  }

  private clearCommitTimer(): void {
    if (this.commitTimer !== null) clearTimeout(this.commitTimer)
    this.commitTimer = null
  }

  private clearTimers(): void {
    this.clearCommitTimer()
    if (this.responseTimer !== null) clearTimeout(this.responseTimer)
    this.responseTimer = null
  }

  private async stopMicrophone(): Promise<void> {
    const stream = this.stream
    this.stream = null
    this.track = null
    for (const track of stream?.getTracks() ?? []) track.stop()
  }

  private async shutdown(): Promise<void> {
    this.clearTimers()
    await this.stopMicrophone()
    this.dc?.close()
    this.pc?.close()
    this.dc = null
    this.pc = null
    this.captureStartedAt = 0
  }
}

const client = new RealtimeClient()

export class RealtimeRecognition implements RecognitionLike {
  lang = 'zh-CN'
  continuous = true
  interimResults = true
  maxAlternatives = 1
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: ((event: RecognitionErrorEvent) => void) | null = null
  onresult: ((event: RecognitionEvent) => void) | null = null

  private readonly sink: Sink
  private stopRequested = false
  private started = false
  private ended = false

  constructor() {
    this.sink = {
      requestId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      onStarted: () => {
        this.started = true
        this.onstart?.()
        if (this.stopRequested) void client.end(this.sink)
      },
      onTranscript: (text) => this.onresult?.(recognitionEvent(text)),
      onUnclear: (message) => this.onerror?.({ error: 'no-speech', message }),
      onFailure: (message) => this.onerror?.({ error: 'network', message }),
      onEnded: () => this.emitEnd(),
    }
  }

  start(): void {
    this.stopRequested = false
    this.started = false
    this.ended = false
    void client.begin(this.sink).catch((error: unknown) => {
      this.onerror?.({ error: 'network', message: error instanceof Error ? error.message : String(error) })
      this.emitEnd()
    })
  }

  stop(): void {
    this.stopRequested = true
    if (!this.started) return
    void client.end(this.sink).catch((error: unknown) => {
      this.onerror?.({ error: 'network', message: error instanceof Error ? error.message : String(error) })
      this.emitEnd()
    })
  }

  abort(): void {
    client.abort(this.sink)
  }

  private emitEnd(): void {
    if (this.ended) return
    this.ended = true
    this.started = false
    this.onend?.()
  }
}

export async function prewarmRealtimeRecognition(): Promise<void> {
  await client.prewarm()
}

export function resetRealtimeRecognition(): void {
  client.reset()
}

;(window as Window & { __woodfloorRealtimeSpeechReset?: () => void }).__woodfloorRealtimeSpeechReset =
  resetRealtimeRecognition
