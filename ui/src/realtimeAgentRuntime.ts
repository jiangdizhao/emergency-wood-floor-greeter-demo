const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000'

const ASR_PROVIDER_KEY = 'woodfloor_asr_provider'
const REALTIME_ASR_PROVIDER = 'gpt-realtime-2'
const VOICE_OUTPUT_KEY = 'woodfloor_voice_output'
const REALTIME_OUTPUT = 'realtime'
const KOKORO_OUTPUT = 'kokoro'
const CONNECTION_TIMEOUT_MS = 15_000
const COMMIT_TIMEOUT_MS = 5_000
const RESPONSE_TIMEOUT_MS = 30_000
const MIC_STABILIZE_MS = 160
const RTP_DRAIN_MS = 220

type PendingCommit = {
  resolve: () => void
  reject: (error: Error) => void
}

type PendingResponse = {
  requestId: string
  purpose: string
  modalities: Array<'text' | 'audio'>
  text: string
  transcript: string
  responseDone: boolean
  audioStopped: boolean
  startedAt: number
  timer: number
  resolve: (value: string) => void
  reject: (error: Error) => void
}

type RealtimeServerEvent = {
  type?: string
  delta?: string
  text?: string
  transcript?: string
  error?: { code?: string; message?: string }
  response?: {
    status?: string
    metadata?: Record<string, unknown>
    status_details?: { error?: { message?: string } }
  }
}

export type RealtimeAgentStatus = {
  connected: boolean
  data_channel: string
  output_mode: string
  last_route: string
  last_latency: Record<string, unknown> | null
}

export type RealtimeAgentRuntime = {
  prewarm: () => Promise<void>
  beginCapture: () => Promise<void>
  endCapture: () => Promise<string>
  abortCapture: () => Promise<void>
  speakExact: (text: string) => Promise<string>
  respondDirect: (userText: string, instruction?: string | null) => Promise<string>
  stopOutput: () => Promise<void>
  status: () => RealtimeAgentStatus
}

type RoutePayload = {
  answer?: string
  response_route?: string
  route_intent?: string
  route_reason?: string
  realtime_instruction?: string | null
  [key: string]: unknown
}

type AudioContextConstructor = new () => AudioContext

declare global {
  interface Window {
    webkitAudioContext?: AudioContextConstructor
    __WOODFLOOR_LANGUAGE__?: string
    __WOODFLOOR_REALTIME_AGENT__?: RealtimeAgentRuntime
  }
}

function selectedLanguage(): 'zh' | 'en' {
  return window.__WOODFLOOR_LANGUAGE__ === 'en' || localStorage.getItem('woodfloor_ui_language') === 'en'
    ? 'en'
    : 'zh'
}

function browserSessionId(): string {
  const key = 'woodfloor_realtime_browser_session_id'
  const existing = sessionStorage.getItem(key)
  if (existing) return existing
  const value = `browser-${crypto.randomUUID()}`
  sessionStorage.setItem(key, value)
  return value
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.href
  return input.url
}

function parseJsonBody(init?: RequestInit): Record<string, unknown> | null {
  try {
    return typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  })
}

function silentWavResponse(): Response {
  const bytes = new Uint8Array([
    82, 73, 70, 70, 36, 0, 0, 0, 87, 65, 86, 69, 102, 109, 116, 32,
    16, 0, 0, 0, 1, 0, 1, 0, 128, 62, 0, 0, 0, 125, 0, 0,
    2, 0, 16, 0, 100, 97, 116, 97, 0, 0, 0, 0,
  ])
  return new Response(bytes, {
    status: 200,
    headers: {
      'Content-Type': 'audio/wav',
      'Cache-Control': 'no-store',
      'X-TTS-Provider': 'gpt-realtime',
    },
  })
}

function recentConversationContext(): string {
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

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function abortError(message: string): Error {
  const error = new Error(message)
  error.name = 'AbortError'
  return error
}

class PersistentRealtimeAgent implements RealtimeAgentRuntime {
  private readonly nativeFetch: typeof window.fetch
  private pc: RTCPeerConnection | null = null
  private dc: RTCDataChannel | null = null
  private sender: RTCRtpSender | null = null
  private silentContext: AudioContext | null = null
  private silentTrack: MediaStreamTrack | null = null
  private silentStream: MediaStream | null = null
  private microphoneStream: MediaStream | null = null
  private remoteAudio: HTMLAudioElement | null = null
  private connectPromise: Promise<void> | null = null
  private captureStartedAt = 0
  private pendingCommit: PendingCommit | null = null
  private pendingResponse: PendingResponse | null = null
  private operationQueue: Promise<unknown> = Promise.resolve()
  private lastRoute = ''
  private lastLatency: Record<string, unknown> | null = null

  constructor(nativeFetch: typeof window.fetch) {
    this.nativeFetch = nativeFetch
  }

  async prewarm(): Promise<void> {
    await this.ensureConnected()
  }

  async beginCapture(): Promise<void> {
    await this.enqueue(async () => {
      await this.stopOutput()
      await this.ensureConnected()
      this.microphoneStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      })
      const track = this.microphoneStream.getAudioTracks()[0] ?? null
      if (!track || !this.sender) throw new Error('No microphone audio track is available.')
      await this.sender.replaceTrack(track)
      await wait(MIC_STABILIZE_MS)
      this.send({ type: 'input_audio_buffer.clear' })
      this.captureStartedAt = performance.now()
      window.dispatchEvent(new CustomEvent('woodfloor:realtime-listening-start'))
    })
  }

  async endCapture(): Promise<string> {
    return await this.enqueue(async () => {
      if (!this.captureStartedAt) throw new Error('Realtime capture was not started.')
      if (performance.now() - this.captureStartedAt < 250) {
        await this.restoreSilentTrack()
        throw new Error('录音时间太短，请看到“正在聆听”后再完整说话。')
      }
      await wait(RTP_DRAIN_MS)
      await this.commitAudio()
      await this.restoreSilentTrack()
      const transcript = await this.createResponse(
        ['text'],
        this.transcriptionInstructions(),
        'speech_understanding',
      )
      this.captureStartedAt = 0
      window.dispatchEvent(new CustomEvent('woodfloor:realtime-listening-stop'))
      return transcript
    })
  }

  async abortCapture(): Promise<void> {
    if (this.dc?.readyState === 'open') this.send({ type: 'input_audio_buffer.clear' })
    await this.restoreSilentTrack()
    this.captureStartedAt = 0
    window.dispatchEvent(new CustomEvent('woodfloor:realtime-listening-stop'))
  }

  async speakExact(text: string): Promise<string> {
    const clean = text.trim()
    if (!clean) return ''
    return await this.enqueue(async () => {
      await this.ensureConnected()
      const instruction =
        selectedLanguage() === 'en'
          ? `Read the following final answer exactly in a warm professional consultant voice. Do not add, remove, summarize, or paraphrase any word:\n${clean}`
          : `请使用自然、亲切、专业的中文顾问语气，逐字朗读下面的最终答复。不得增加、删除、总结或改写任何内容：\n${clean}`
      const spoken = await this.createResponse(['audio'], instruction, 'exact_backend_answer')
      return spoken || clean
    })
  }

  async respondDirect(userText: string, instruction?: string | null): Promise<string> {
    const clean = userText.trim()
    return await this.enqueue(async () => {
      await this.ensureConnected()
      const prompt = [
        selectedLanguage() === 'en'
          ? 'You are Xiao Mu, the voice consultant at Senjing Flooring Living Gallery.'
          : '你是森境地板生活馆的语音顾问“小木”。',
        instruction ?? '',
        selectedLanguage() === 'en'
          ? `The user's normalized utterance is: ${clean}`
          : `用户最终确认的话是：${clean}`,
        selectedLanguage() === 'en'
          ? 'Answer now in no more than two short sentences.'
          : '现在直接回答用户，最多两句，保持简短自然。',
      ]
        .filter(Boolean)
        .join('\n')
      return await this.createResponse(['audio'], prompt, 'realtime_direct')
    })
  }

  async stopOutput(): Promise<void> {
    const pending = this.pendingResponse
    if (pending?.modalities.includes('audio')) {
      window.clearTimeout(pending.timer)
      this.pendingResponse = null
      pending.reject(abortError('Realtime speech was interrupted by the user.'))
    }
    if (this.dc?.readyState === 'open') {
      this.safeSend({ type: 'response.cancel' })
      this.safeSend({ type: 'output_audio_buffer.clear' })
    }
    this.remoteAudio?.pause()
    window.dispatchEvent(new CustomEvent('woodfloor:realtime-speaking-stop'))
  }

  status(): RealtimeAgentStatus {
    return {
      connected: this.pc?.connectionState === 'connected',
      data_channel: this.dc?.readyState ?? 'closed',
      output_mode: localStorage.getItem(VOICE_OUTPUT_KEY) ?? REALTIME_OUTPUT,
      last_route: this.lastRoute,
      last_latency: this.lastLatency,
    }
  }

  setRouteDiagnostics(route: string, latency: Record<string, unknown>): void {
    this.lastRoute = route
    this.lastLatency = latency
  }

  private async enqueue<T>(operation: () => Promise<T>): Promise<T> {
    const next = this.operationQueue.then(operation, operation)
    this.operationQueue = next.catch(() => undefined)
    return await next
  }

  private async ensureConnected(): Promise<void> {
    if (
      this.pc &&
      this.dc?.readyState === 'open' &&
      ['connected', 'connecting', 'new'].includes(this.pc.connectionState)
    ) {
      if (this.remoteAudio?.paused) await this.remoteAudio.play().catch(() => undefined)
      return
    }
    if (this.connectPromise) return await this.connectPromise
    this.connectPromise = this.connect()
    try {
      await this.connectPromise
    } finally {
      this.connectPromise = null
    }
  }

  private async connect(): Promise<void> {
    await this.shutdownConnection()
    const statusResponse = await this.nativeFetch(`${API_BASE_URL}/api/realtime/status`, {
      headers: { Accept: 'application/json' },
    })
    if (!statusResponse.ok) throw new Error(`Realtime status failed: ${statusResponse.status}`)
    const status = (await statusResponse.json()) as { configured?: boolean; enabled?: boolean }
    if (!status.configured || !status.enabled) throw new Error('GPT Realtime is not configured.')

    this.createSilentTrack()
    if (!this.silentTrack || !this.silentStream) throw new Error('Could not create a silent WebRTC track.')

    const pc = new RTCPeerConnection()
    const dc = pc.createDataChannel('oai-events')
    this.pc = pc
    this.dc = dc
    this.sender = pc.addTrack(this.silentTrack, this.silentStream)

    const remoteAudio = document.createElement('audio')
    remoteAudio.autoplay = true
    remoteAudio.playsInline = true
    remoteAudio.hidden = true
    document.body.appendChild(remoteAudio)
    this.remoteAudio = remoteAudio

    pc.addEventListener('track', (event) => {
      remoteAudio.srcObject = event.streams[0] ?? new MediaStream([event.track])
      void remoteAudio.play().catch(() => undefined)
    })
    dc.addEventListener('message', (event: MessageEvent<string>) => this.handleServerEvent(event))
    pc.addEventListener('connectionstatechange', () => {
      if (['failed', 'closed'].includes(pc.connectionState)) {
        this.rejectPending(new Error('GPT Realtime WebRTC connection was lost.'))
      }
    })

    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const sdp = pc.localDescription?.sdp ?? offer.sdp
    if (!sdp) throw new Error('Could not create a WebRTC SDP offer.')

    const sessionResponse = await this.nativeFetch(
      `${API_BASE_URL}/api/realtime/session?session_id=${encodeURIComponent(browserSessionId())}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/sdp' },
        body: sdp,
      },
    )
    if (!sessionResponse.ok) {
      const detail = await sessionResponse.text().catch(() => '')
      throw new Error(`Realtime session failed: ${sessionResponse.status} ${detail}`)
    }
    await pc.setRemoteDescription({ type: 'answer', sdp: await sessionResponse.text() })
    await this.waitForDataChannel(dc)
    this.send({
      type: 'session.update',
      session: {
        type: 'realtime',
        output_modalities: ['audio'],
        instructions:
          selectedLanguage() === 'en'
            ? 'You are Xiao Mu, a concise, warm and professional flooring voice consultant. Never invent product facts, prices, promotions, stock, or completed actions.'
            : '你是森境地板生活馆的语音顾问小木。表达简洁、自然、亲切、专业；不得编造产品事实、价格、活动、库存或已经完成的操作。',
        audio: {
          input: { turn_detection: null },
          output: { voice: 'marin', speed: 1.0 },
        },
      },
    })
    window.dispatchEvent(new CustomEvent('woodfloor:realtime-connected'))
  }

  private createSilentTrack(): void {
    if (this.silentTrack && this.silentStream) return
    const AudioContextClass = window.AudioContext ?? window.webkitAudioContext
    if (!AudioContextClass) throw new Error('Web Audio is unavailable.')
    const context = new AudioContextClass()
    const destination = context.createMediaStreamDestination()
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    gain.gain.value = 0
    oscillator.connect(gain)
    gain.connect(destination)
    oscillator.start()
    this.silentContext = context
    this.silentStream = destination.stream
    this.silentTrack = destination.stream.getAudioTracks()[0] ?? null
  }

  private async restoreSilentTrack(): Promise<void> {
    if (this.sender && this.silentTrack) await this.sender.replaceTrack(this.silentTrack)
    for (const track of this.microphoneStream?.getTracks() ?? []) track.stop()
    this.microphoneStream = null
  }

  private commitAudio(): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        if (this.pendingCommit) this.pendingCommit = null
        reject(new Error('GPT Realtime did not confirm the audio buffer.'))
      }, COMMIT_TIMEOUT_MS)
      this.pendingCommit = {
        resolve: () => {
          window.clearTimeout(timer)
          this.pendingCommit = null
          resolve()
        },
        reject: (error) => {
          window.clearTimeout(timer)
          this.pendingCommit = null
          reject(error)
        },
      }
      this.send({ type: 'input_audio_buffer.commit' })
    })
  }

  private createResponse(
    modalities: Array<'text' | 'audio'>,
    instructions: string,
    purpose: string,
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      if (this.pendingResponse) {
        reject(new Error('Another GPT Realtime response is still active.'))
        return
      }
      const requestId = `${purpose}-${Date.now()}-${Math.random().toString(16).slice(2)}`
      const startedAt = performance.now()
      const timer = window.setTimeout(() => {
        if (this.pendingResponse?.requestId !== requestId) return
        this.safeSend({ type: 'response.cancel' })
        this.pendingResponse = null
        reject(new Error('GPT Realtime response timed out.'))
      }, RESPONSE_TIMEOUT_MS)
      this.pendingResponse = {
        requestId,
        purpose,
        modalities,
        text: '',
        transcript: '',
        responseDone: false,
        audioStopped: !modalities.includes('audio'),
        startedAt,
        timer,
        resolve,
        reject,
      }
      this.send({
        type: 'response.create',
        response: {
          conversation: 'none',
          output_modalities: modalities,
          metadata: { purpose, request_id: requestId },
          instructions,
        },
      })
    })
  }

  private maybeResolveResponse(): void {
    const pending = this.pendingResponse
    if (!pending || !pending.responseDone || !pending.audioStopped) return
    window.clearTimeout(pending.timer)
    this.pendingResponse = null
    const text = (pending.transcript || pending.text).trim()
    this.lastLatency = {
      purpose: pending.purpose,
      response_ms: Math.round(performance.now() - pending.startedAt),
    }
    pending.resolve(text)
  }

  private handleServerEvent(message: MessageEvent<string>): void {
    let event: RealtimeServerEvent
    try {
      event = JSON.parse(message.data) as RealtimeServerEvent
    } catch {
      return
    }

    if (event.type === 'input_audio_buffer.committed') {
      this.pendingCommit?.resolve()
      return
    }
    if (event.type === 'response.output_text.delta' && this.pendingResponse) {
      this.pendingResponse.text += event.delta ?? ''
      return
    }
    if (event.type === 'response.output_text.done' && this.pendingResponse) {
      this.pendingResponse.text = event.text ?? this.pendingResponse.text
      return
    }
    if (event.type === 'response.output_audio_transcript.delta' && this.pendingResponse) {
      this.pendingResponse.transcript += event.delta ?? ''
      return
    }
    if (event.type === 'response.output_audio_transcript.done' && this.pendingResponse) {
      this.pendingResponse.transcript = event.transcript ?? this.pendingResponse.transcript
      return
    }
    if (event.type === 'output_audio_buffer.started') {
      window.dispatchEvent(new CustomEvent('woodfloor:realtime-speaking-start'))
      return
    }
    if (event.type === 'output_audio_buffer.stopped') {
      if (this.pendingResponse) this.pendingResponse.audioStopped = true
      window.dispatchEvent(new CustomEvent('woodfloor:realtime-speaking-stop'))
      this.maybeResolveResponse()
      return
    }
    if (event.type === 'response.done') {
      const pending = this.pendingResponse
      if (!pending) return
      const responseRequestId = event.response?.metadata?.request_id
      if (typeof responseRequestId === 'string' && responseRequestId !== pending.requestId) return
      if (event.response?.status === 'failed') {
        const detail = event.response.status_details?.error?.message ?? 'GPT Realtime response failed.'
        window.clearTimeout(pending.timer)
        this.pendingResponse = null
        pending.reject(new Error(detail))
        return
      }
      pending.responseDone = true
      this.maybeResolveResponse()
      return
    }
    if (event.type === 'error') {
      const code = event.error?.code ?? ''
      if (['response_cancel_not_active', 'input_audio_buffer_clear_empty'].includes(code)) return
      const error = new Error(event.error?.message ?? 'GPT Realtime returned an unknown error.')
      if (this.pendingCommit) this.pendingCommit.reject(error)
      else if (this.pendingResponse) {
        const pending = this.pendingResponse
        window.clearTimeout(pending.timer)
        this.pendingResponse = null
        pending.reject(error)
      }
    }
  }

  private transcriptionInstructions(): string {
    return `
You are a speech-understanding layer, not a conversational assistant.
Return only the user's final intended utterance as plain text. Do not answer.
Language: ${selectedLanguage() === 'en' ? 'English' : 'Chinese Mandarin'}.
Recent conversation:
${recentConversationContext()}
Later explicit corrections override earlier uncertain words.
Chinese correction signals such as “不”, “不是”, “不对”, “我是说”, “应该是” and character explanations are authoritative.
Example: “我喜欢钱会色，不，浅灰色，深浅的浅，灰色的灰” becomes “我喜欢浅灰色”.
Relevant terms include 浅灰色、深灰色、原木色、深胡桃色、SPC、多层实木、强化地板、防水、耐磨、地暖、宠物、客厅、卧室、全屋.
Never invent a preference. If genuinely unintelligible, output exactly __UNCLEAR__.
Output only normalized plain text without labels, JSON, Markdown, or quotation marks.
`.trim()
  }

  private send(event: Record<string, unknown>): void {
    if (this.dc?.readyState !== 'open') throw new Error('GPT Realtime data channel is not open.')
    this.dc.send(JSON.stringify(event))
  }

  private safeSend(event: Record<string, unknown>): void {
    if (this.dc?.readyState === 'open') this.dc.send(JSON.stringify(event))
  }

  private waitForDataChannel(channel: RTCDataChannel): Promise<void> {
    if (channel.readyState === 'open') return Promise.resolve()
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        cleanup()
        reject(new Error('Timed out while opening GPT Realtime data channel.'))
      }, CONNECTION_TIMEOUT_MS)
      const cleanup = () => {
        window.clearTimeout(timer)
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

  private rejectPending(error: Error): void {
    this.pendingCommit?.reject(error)
    const pending = this.pendingResponse
    if (pending) {
      window.clearTimeout(pending.timer)
      this.pendingResponse = null
      pending.reject(error)
    }
  }

  private async shutdownConnection(): Promise<void> {
    this.rejectPending(new Error('GPT Realtime connection reset.'))
    await this.restoreSilentTrack().catch(() => undefined)
    this.dc?.close()
    this.pc?.close()
    this.remoteAudio?.remove()
    this.dc = null
    this.pc = null
    this.sender = null
    this.remoteAudio = null
  }
}

if (!localStorage.getItem(ASR_PROVIDER_KEY)) localStorage.setItem(ASR_PROVIDER_KEY, REALTIME_ASR_PROVIDER)
if (!localStorage.getItem(VOICE_OUTPUT_KEY)) localStorage.setItem(VOICE_OUTPUT_KEY, REALTIME_OUTPUT)

const nativeFetch = window.fetch.bind(window)
const agent = new PersistentRealtimeAgent(nativeFetch)
window.__WOODFLOOR_REALTIME_AGENT__ = agent

let lastAnswer = ''
let skipNextTtsText = ''

window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const url = requestUrl(input)
  const body = parseJsonBody(init)

  if (url.includes('/api/chat') && typeof body?.text === 'string') {
    const startedAt = performance.now()
    try {
      const routeResponse = await nativeFetch(`${API_BASE_URL}/api/interaction/route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify(body),
      })
      if (!routeResponse.ok) {
        const detail = await routeResponse.text().catch(() => '')
        throw new Error(`Interaction route failed: ${routeResponse.status} ${detail}`)
      }
      const payload = (await routeResponse.json()) as RoutePayload
      const route = payload.response_route ?? 'terra'

      if (route === 'repeat_last') {
        payload.answer =
          lastAnswer ||
          (selectedLanguage() === 'en'
            ? 'There is no previous answer to repeat yet.'
            : '目前还没有上一条答复可以重复。')
      } else if (route === 'realtime_direct') {
        payload.answer = await agent.respondDirect(String(body.text), payload.realtime_instruction)
        skipNextTtsText = String(payload.answer ?? '').trim()
      } else if (route === 'stop_speaking') {
        await agent.stopOutput()
      }

      if (typeof payload.answer === 'string' && payload.answer.trim()) lastAnswer = payload.answer.trim()
      const diagnostics = {
        route,
        intent: payload.route_intent,
        reason: payload.route_reason,
        latency_ms: Math.round(performance.now() - startedAt),
      }
      agent.setRouteDiagnostics(route, diagnostics)
      console.info('[voice-route]', diagnostics)
      return jsonResponse(payload)
    } catch (error) {
      console.warn('Routed interaction failed; using legacy /api/chat:', error)
      return await nativeFetch(input, init)
    }
  }

  if (url.includes('/api/tts') && typeof body?.text === 'string') {
    const mode = localStorage.getItem(VOICE_OUTPUT_KEY) ?? REALTIME_OUTPUT
    if (mode === REALTIME_OUTPUT) {
      const text = String(body.text).trim()
      if (skipNextTtsText && text === skipNextTtsText) {
        skipNextTtsText = ''
        return silentWavResponse()
      }
      try {
        await agent.speakExact(text)
        return silentWavResponse()
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') return silentWavResponse()
        console.warn('GPT Realtime audio output failed; falling back to Kokoro chain:', error)
        const headers = new Headers(init?.headers)
        headers.set('Content-Type', 'application/json; charset=utf-8')
        return await nativeFetch(input, {
          ...init,
          headers,
          body: JSON.stringify({ ...body, provider: 'local' }),
        })
      }
    }
  }

  return await nativeFetch(input, init)
}

function installVoiceOutputControl(): void {
  if (document.getElementById('woodfloor-voice-output-control')) return
  const wrapper = document.createElement('label')
  wrapper.id = 'woodfloor-voice-output-control'
  wrapper.style.cssText = [
    'position:fixed',
    'right:18px',
    'bottom:58px',
    'z-index:95',
    'display:flex',
    'align-items:center',
    'gap:8px',
    'padding:7px 10px',
    'border:1px solid rgba(112,76,55,.2)',
    'border-radius:12px',
    'background:rgba(255,253,249,.94)',
    'box-shadow:0 8px 22px rgba(71,47,34,.12)',
    'font:700 12px Inter,"Noto Sans SC","Microsoft YaHei",sans-serif',
    'color:#76503b',
    'backdrop-filter:blur(10px)',
  ].join(';')
  const title = document.createElement('span')
  title.textContent = selectedLanguage() === 'en' ? 'Voice' : '语音输出'
  const select = document.createElement('select')
  select.style.cssText = 'border:0;background:transparent;color:#5f4335;font:inherit;outline:none'
  const realtimeOption = document.createElement('option')
  realtimeOption.value = REALTIME_OUTPUT
  realtimeOption.textContent = selectedLanguage() === 'en' ? 'GPT Realtime (default)' : 'GPT Realtime（默认）'
  const kokoroOption = document.createElement('option')
  kokoroOption.value = KOKORO_OUTPUT
  kokoroOption.textContent = selectedLanguage() === 'en' ? 'Kokoro local voice' : 'Kokoro 本地语音'
  select.append(realtimeOption, kokoroOption)
  select.value = localStorage.getItem(VOICE_OUTPUT_KEY) ?? REALTIME_OUTPUT
  select.addEventListener('change', () => {
    localStorage.setItem(VOICE_OUTPUT_KEY, select.value)
    if (select.value === KOKORO_OUTPUT) void agent.stopOutput().catch(() => undefined)
    window.dispatchEvent(new CustomEvent('woodfloor:voice-output-changed', { detail: select.value }))
  })
  wrapper.append(title, select)
  document.body.appendChild(wrapper)
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', installVoiceOutputControl, { once: true })
} else {
  installVoiceOutputControl()
}

window.setTimeout(() => {
  if ((localStorage.getItem(VOICE_OUTPUT_KEY) ?? REALTIME_OUTPUT) === REALTIME_OUTPUT) {
    void agent.prewarm().catch((error) => console.warn('Realtime prewarm deferred:', error))
  }
}, 500)

export function getRealtimeAgentRuntime(): RealtimeAgentRuntime {
  return agent
}
