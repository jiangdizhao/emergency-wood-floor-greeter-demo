export type RecognitionAlternative = {
  transcript: string
  confidence?: number
}

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

export type RecognitionErrorEvent = {
  error: string
  message?: string
}

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

type RealtimeServerEvent = {
  type?: string
  delta?: string
  text?: string
  response_id?: string
  response?: {
    id?: string
    status?: string
    status_details?: { error?: { message?: string } }
    metadata?: Record<string, unknown>
    output?: Array<{
      content?: Array<{
        text?: string
        transcript?: string
      }>
    }>
  }
  error?: { message?: string; code?: string }
}

type RealtimeRecognitionSink = {
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
const RESPONSE_TIMEOUT_MS = 30_000

function currentSessionId(): string {
  const sessionFromWindow = (window as Window & { __WOODFLOOR_SESSION_ID__?: string }).__WOODFLOOR_SESSION_ID__
  if (sessionFromWindow?.trim()) return sessionFromWindow.trim()
  const storageKey = 'woodfloor_realtime_browser_session_id'
  const existing = window.sessionStorage.getItem(storageKey)
  if (existing) return existing
  const created = `browser-${crypto.randomUUID()}`
  window.sessionStorage.setItem(storageKey, created)
  return created
}

function selectedLanguage(): 'zh' | 'en' {
  const configured = (window as Window & { __WOODFLOOR_LANGUAGE__?: string }).__WOODFLOOR_LANGUAGE__
  return configured === 'en' || window.localStorage.getItem('woodfloor_ui_language') === 'en' ? 'en' : 'zh'
}

export function realtimeAsrSelected(): boolean {
  return window.localStorage.getItem(PROVIDER_STORAGE_KEY) === REALTIME_PROVIDER
}

function redactSensitiveText(text: string): string {
  return text
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[email redacted]')
    .replace(/(?:\+?\d[\d\s()-]{7,}\d)/g, '[phone redacted]')
}

function recentConversationContext(): string {
  const rows = Array.from(document.querySelectorAll<HTMLElement>('.chat-log .message-row')).slice(-8)
  const lines = rows
    .map((row) => {
      const role = row.classList.contains('customer') ? 'User' : 'Assistant'
      const text = row.querySelector('p')?.textContent?.replace(/\s+/g, ' ').trim() ?? ''
      return text ? `${role}: ${redactSensitiveText(text)}` : ''
    })
    .filter(Boolean)
  return lines.length ? lines.join('\n') : '(no prior visible conversation)'
}

function recognitionInstructions(): string {
  const language = selectedLanguage()
  const context = recentConversationContext()
  const domainTerms =
    language === 'en'
      ? 'light grey, grey, natural oak, dark walnut, cream white, SPC, engineered wood, laminate, waterproof, wear resistance, underfloor heating, pets, living room, bedroom, whole home'
      : '浅灰色、浅灰、灰色、深灰色、原木色、深胡桃色、奶油白、SPC、多层实木、强化地板、防水、耐磨、地暖、宠物、客厅、卧室、全屋'

  return `
You are a speech-understanding layer, not a conversational assistant.
Listen to the complete committed audio turn and output only the user's final intended utterance as plain text.
Do not answer, advise, recommend, summarize, or mention uncertainty unless the audio is genuinely unintelligible.

Language: ${language === 'en' ? 'English' : 'Chinese Mandarin'}.
Recent visible conversation:
${context}

Relevant flooring vocabulary:
${domainTerms}

Self-correction policy:
- Later explicit corrections override earlier uncertain words.
- In Chinese, correction signals such as “不”, “不是”, “不对”, “我是说”, “应该是” and character explanations are authoritative.
- Example: “我喜欢钱会色，不，浅灰色，深浅的浅，灰色的灰” must normalize to “我喜欢浅灰色”.
- Keep requirements the user did not retract.
- Use context only to resolve plausible acoustic ambiguity. Never invent a preference.
- If the audio is truly unintelligible or two interpretations remain equally plausible, output exactly __UNCLEAR__.
- Otherwise output only the normalized utterance, with no label, quotation marks, JSON, Markdown, or commentary.
`.trim()
}

function stripModelFormatting(value: string): string {
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

function extractResponseText(event: RealtimeServerEvent): string {
  const direct = event.text?.trim()
  if (direct) return direct
  const outputs = event.response?.output ?? []
  const parts: string[] = []
  for (const output of outputs) {
    for (const content of output.content ?? []) {
      if (content.text?.trim()) parts.push(content.text.trim())
      else if (content.transcript?.trim()) parts.push(content.transcript.trim())
    }
  }
  return parts.join(' ').trim()
}

function makeRecognitionEvent(text: string): RecognitionEvent {
  const alternative: RecognitionAlternative = { transcript: text, confidence: 1 }
  const result = [alternative] as unknown as RecognitionResult
  result.isFinal = true
  return { results: [result] as unknown as RecognitionEvent['results'] }
}

class RealtimeWebRtcClient {
  private peerConnection: RTCPeerConnection | null = null
  private dataChannel: RTCDataChannel | null = null
  private mediaStream: MediaStream | null = null
  private microphoneTrack: MediaStreamTrack | null = null
  private connectPromise: Promise<void> | null = null
  private activeSink: RealtimeRecognitionSink | null = null
  private captureStartedAt = 0
  private outputText = ''
  private responseTimer: number | null = null
  private responseInProgress = false

  async beginTurn(sink: RealtimeRecognitionSink): Promise<void> {
    await this.ensureConnected()
    if (!this.dataChannel || this.dataChannel.readyState !== 'open' || !this.microphoneTrack) {
      throw new Error('GPT Realtime connection is not ready.')
    }

    this.cancelResponseTimer()
    this.activeSink = sink
    this.outputText = ''
    this.captureStartedAt = performance.now()
    if (this.responseInProgress) this.send({ type: 'response.cancel' })
    this.send({ type: 'input_audio_buffer.clear' })
    this.microphoneTrack.enabled = true
    sink.onStarted()
  }

  endTurn(sink: RealtimeRecognitionSink): void {
    if (this.activeSink !== sink) return
    if (this.microphoneTrack) this.microphoneTrack.enabled = false

    const durationMs = performance.now() - this.captureStartedAt
    if (durationMs < MIN_CAPTURE_MS) {
      this.activeSink = null
      sink.onUnclear('录音时间太短，请按住按钮并完整说完。')
      sink.onEnded()
      return
    }

    this.send({ type: 'input_audio_buffer.commit' })
    this.responseInProgress = true
    this.send({
      type: 'response.create',
      response: {
        output_modalities: ['text'],
        metadata: {
          purpose: 'speech_understanding',
          request_id: sink.requestId,
        },
        instructions: recognitionInstructions(),
      },
    })

    this.responseTimer = window.setTimeout(() => {
      if (this.activeSink !== sink) return
      this.activeSink = null
      this.responseInProgress = false
      this.send({ type: 'response.cancel' })
      sink.onFailure('GPT Realtime 语音理解超时，请重试或切回浏览器识别。')
      sink.onEnded()
    }, RESPONSE_TIMEOUT_MS)
  }

  abortTurn(sink: RealtimeRecognitionSink): void {
    if (this.activeSink !== sink) return
    if (this.microphoneTrack) this.microphoneTrack.enabled = false
    if (this.responseInProgress) this.send({ type: 'response.cancel' })
    this.responseInProgress = false
    this.send({ type: 'input_audio_buffer.clear' })
    this.cancelResponseTimer()
    this.activeSink = null
    sink.onEnded()
  }

  async prewarm(): Promise<void> {
    await this.ensureConnected()
  }

  reset(): void {
    this.cancelResponseTimer()
    if (this.microphoneTrack) this.microphoneTrack.enabled = false
    for (const track of this.mediaStream?.getTracks() ?? []) track.stop()
    this.dataChannel?.close()
    this.peerConnection?.close()
    this.peerConnection = null
    this.dataChannel = null
    this.mediaStream = null
    this.microphoneTrack = null
    this.connectPromise = null
    this.responseInProgress = false
    const sink = this.activeSink
    this.activeSink = null
    if (sink) {
      sink.onFailure('GPT Realtime 连接已重置。')
      sink.onEnded()
    }
  }

  private async ensureConnected(): Promise<void> {
    if (
      this.peerConnection &&
      this.dataChannel?.readyState === 'open' &&
      ['connected', 'connecting', 'new'].includes(this.peerConnection.connectionState)
    ) {
      return
    }
    if (this.connectPromise) return this.connectPromise
    this.connectPromise = this.connect()
    try {
      await this.connectPromise
    } finally {
      this.connectPromise = null
    }
  }

  private async connect(): Promise<void> {
    this.resetTransportOnly()
    const pc = new RTCPeerConnection()
    const dc = pc.createDataChannel('oai-events')
    this.peerConnection = pc
    this.dataChannel = dc

    dc.addEventListener('message', (event) => this.handleServerMessage(event))
    pc.addEventListener('connectionstatechange', () => {
      if (['failed', 'closed', 'disconnected'].includes(pc.connectionState)) {
        const sink = this.activeSink
        if (sink) {
          this.activeSink = null
          sink.onFailure('GPT Realtime WebRTC 连接已断开。')
          sink.onEnded()
        }
      }
    })

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    })
    const track = stream.getAudioTracks()[0]
    if (!track) {
      for (const mediaTrack of stream.getTracks()) mediaTrack.stop()
      throw new Error('No microphone audio track is available.')
    }
    track.enabled = false
    this.mediaStream = stream
    this.microphoneTrack = track
    pc.addTrack(track, stream)

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const localSdp = pc.localDescription?.sdp ?? offer.sdp
    if (!localSdp) throw new Error('Could not create WebRTC SDP offer.')

    const response = await fetch(
      `${API_BASE_URL}/api/realtime/session?session_id=${encodeURIComponent(currentSessionId())}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: localSdp,
      },
    )
    if (!response.ok) {
      const detail = await response.text().catch(() => '')
      throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ''}`)
    }
    const answerSdp = await response.text()
    await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp })
    await this.waitForDataChannel(dc)

    this.send({
      type: 'session.update',
      session: {
        type: 'realtime',
        output_modalities: ['text'],
        audio: {
          input: {
            turn_detection: null,
          },
        },
      },
    })
  }

  private waitForDataChannel(channel: RTCDataChannel): Promise<void> {
    if (channel.readyState === 'open') return Promise.resolve()
    return new Promise<void>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        cleanup()
        reject(new Error('Timed out while opening GPT Realtime data channel.'))
      }, DATA_CHANNEL_TIMEOUT_MS)
      const onOpen = () => {
        cleanup()
        resolve()
      }
      const onError = () => {
        cleanup()
        reject(new Error('Could not open GPT Realtime data channel.'))
      }
      const cleanup = () => {
        window.clearTimeout(timeout)
        channel.removeEventListener('open', onOpen)
        channel.removeEventListener('error', onError)
      }
      channel.addEventListener('open', onOpen)
      channel.addEventListener('error', onError)
    })
  }

  private send(event: Record<string, unknown>): void {
    if (this.dataChannel?.readyState !== 'open') return
    this.dataChannel.send(JSON.stringify(event))
  }

  private handleServerMessage(message: MessageEvent<string>): void {
    let event: RealtimeServerEvent
    try {
      event = JSON.parse(message.data) as RealtimeServerEvent
    } catch {
      return
    }

    if (event.type === 'response.output_text.delta' && typeof event.delta === 'string') {
      this.outputText += event.delta
      return
    }

    if (event.type === 'response.output_text.done' && typeof event.text === 'string') {
      this.outputText = event.text
      return
    }

    if (event.type === 'response.created') {
      this.responseInProgress = true
      return
    }

    if (event.type === 'error') {
      if (['response_cancel_not_active', 'input_audio_buffer_clear_empty'].includes(event.error?.code ?? '')) return
      const sink = this.activeSink
      if (!sink) return
      this.cancelResponseTimer()
      this.responseInProgress = false
      this.activeSink = null
      sink.onFailure(event.error?.message || 'GPT Realtime returned an unknown error.')
      sink.onEnded()
      return
    }

    if (event.type !== 'response.done') return
    const sink = this.activeSink
    if (!sink) return
    const requestId = event.response?.metadata?.request_id
    if (typeof requestId === 'string' && requestId !== sink.requestId) return

    this.cancelResponseTimer()
    this.responseInProgress = false
    this.activeSink = null
    const rawText = this.outputText || extractResponseText(event)
    this.outputText = ''
    const normalized = stripModelFormatting(rawText)
    const failed = event.response?.status === 'failed'
    if (failed) {
      sink.onFailure(event.response?.status_details?.error?.message || 'GPT Realtime response failed.')
    } else if (!normalized || normalized === '__UNCLEAR__') {
      sink.onUnclear('周围声音较大或语音仍有歧义，请靠近麦克风后再说一次。')
    } else {
      sink.onTranscript(normalized)
    }
    sink.onEnded()
  }

  private cancelResponseTimer(): void {
    if (this.responseTimer !== null) {
      window.clearTimeout(this.responseTimer)
      this.responseTimer = null
    }
  }

  private resetTransportOnly(): void {
    this.cancelResponseTimer()
    for (const track of this.mediaStream?.getTracks() ?? []) track.stop()
    this.dataChannel?.close()
    this.peerConnection?.close()
    this.peerConnection = null
    this.dataChannel = null
    this.mediaStream = null
    this.microphoneTrack = null
  }
}

const realtimeClient = new RealtimeWebRtcClient()

export class RealtimeRecognition implements RecognitionLike {
  lang = 'zh-CN'
  continuous = true
  interimResults = true
  maxAlternatives = 1
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: ((event: RecognitionErrorEvent) => void) | null = null
  onresult: ((event: RecognitionEvent) => void) | null = null

  private readonly sink: RealtimeRecognitionSink
  private stopRequested = false
  private ended = false

  constructor() {
    const requestId = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    this.sink = {
      requestId,
      onStarted: () => {
        this.onstart?.()
        if (this.stopRequested) realtimeClient.endTurn(this.sink)
      },
      onTranscript: (text) => this.onresult?.(makeRecognitionEvent(text)),
      onUnclear: (message) => this.onerror?.({ error: 'no-speech', message }),
      onFailure: (message) => this.onerror?.({ error: 'network', message }),
      onEnded: () => this.emitEnd(),
    }
  }

  start(): void {
    this.stopRequested = false
    this.ended = false
    void realtimeClient.beginTurn(this.sink).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error)
      this.onerror?.({ error: 'network', message })
      this.emitEnd()
    })
  }

  stop(): void {
    this.stopRequested = true
    realtimeClient.endTurn(this.sink)
  }

  abort(): void {
    realtimeClient.abortTurn(this.sink)
  }

  private emitEnd(): void {
    if (this.ended) return
    this.ended = true
    this.onend?.()
  }
}

export async function prewarmRealtimeRecognition(): Promise<void> {
  await realtimeClient.prewarm()
}

export function resetRealtimeRecognition(): void {
  realtimeClient.reset()
}

const speechWindow = window as Window & {
  __woodfloorRealtimeSpeechReset?: () => void
}
speechWindow.__woodfloorRealtimeSpeechReset = resetRealtimeRecognition
