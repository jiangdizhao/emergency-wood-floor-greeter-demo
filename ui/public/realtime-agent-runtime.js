(() => {
  const API_BASE_URL = 'http://127.0.0.1:8000'
  const ASR_PROVIDER_KEY = 'woodfloor_asr_provider'
  const REALTIME_ASR_PROVIDER = 'gpt-realtime-2'
  const VOICE_OUTPUT_KEY = 'woodfloor_voice_output'
  const REALTIME_OUTPUT = 'realtime'
  const KOKORO_OUTPUT = 'kokoro'
  const CONNECTION_TIMEOUT_MS = 15000
  const COMMIT_TIMEOUT_MS = 5000
  const RESPONSE_TIMEOUT_MS = 30000
  const MIC_STABILIZE_MS = 160
  const RTP_DRAIN_MS = 220

  if (!localStorage.getItem(ASR_PROVIDER_KEY)) {
    localStorage.setItem(ASR_PROVIDER_KEY, REALTIME_ASR_PROVIDER)
  }
  if (!localStorage.getItem(VOICE_OUTPUT_KEY)) {
    localStorage.setItem(VOICE_OUTPUT_KEY, REALTIME_OUTPUT)
  }

  const nativeFetch = window.fetch.bind(window)
  const wait = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms))

  function language() {
    return window.__WOODFLOOR_LANGUAGE__ === 'en' || localStorage.getItem('woodfloor_ui_language') === 'en'
      ? 'en'
      : 'zh'
  }

  function browserSessionId() {
    const key = 'woodfloor_realtime_browser_session_id'
    const existing = sessionStorage.getItem(key)
    if (existing) return existing
    const value = `browser-${crypto.randomUUID()}`
    sessionStorage.setItem(key, value)
    return value
  }

  function requestUrl(input) {
    if (typeof input === 'string') return input
    if (input instanceof URL) return input.href
    return input && typeof input.url === 'string' ? input.url : ''
  }

  function parseBody(init) {
    try {
      return init && typeof init.body === 'string' ? JSON.parse(init.body) : null
    } catch {
      return null
    }
  }

  function jsonResponse(payload) {
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    })
  }

  function silentWavResponse() {
    // Valid 44-byte mono PCM WAV with zero samples. Existing React audio code can
    // consume it after Realtime has already finished playing the real response.
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

  class RealtimeAgentRuntime {
    constructor() {
      this.pc = null
      this.dc = null
      this.sender = null
      this.silentContext = null
      this.silentTrack = null
      this.silentStream = null
      this.microphoneStream = null
      this.microphoneTrack = null
      this.remoteAudio = null
      this.connectPromise = null
      this.captureStartedAt = 0
      this.pendingCommit = null
      this.pendingResponse = null
      this.operationQueue = Promise.resolve()
      this.lastSpokenText = ''
      this.lastRoute = ''
      this.lastLatency = null
      this.outputStarted = false
    }

    async prewarm() {
      await this.ensureConnected()
    }

    async beginCapture() {
      return this.enqueue(async () => {
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
        this.microphoneTrack = this.microphoneStream.getAudioTracks()[0] || null
        if (!this.microphoneTrack) throw new Error('No microphone audio track is available.')
        await this.sender.replaceTrack(this.microphoneTrack)
        await wait(MIC_STABILIZE_MS)
        this.send({ type: 'input_audio_buffer.clear' })
        this.captureStartedAt = performance.now()
        window.dispatchEvent(new CustomEvent('woodfloor:realtime-listening-start'))
      })
    }

    async endCapture() {
      return this.enqueue(async () => {
        if (!this.captureStartedAt) throw new Error('Realtime capture was not started.')
        if (performance.now() - this.captureStartedAt < 250) {
          await this.restoreSilentTrack()
          throw new Error('录音时间太短，请看到“正在聆听”后再完整说话。')
        }
        await wait(RTP_DRAIN_MS)
        await this.commitAudio()
        await this.restoreSilentTrack()
        const transcript = await this.createTextResponse(
          this.transcriptionInstructions(),
          'speech_understanding',
        )
        this.captureStartedAt = 0
        window.dispatchEvent(new CustomEvent('woodfloor:realtime-listening-stop'))
        return transcript
      })
    }

    async abortCapture() {
      this.send({ type: 'input_audio_buffer.clear' })
      await this.restoreSilentTrack()
      this.captureStartedAt = 0
      window.dispatchEvent(new CustomEvent('woodfloor:realtime-listening-stop'))
    }

    async speakExact(text) {
      const clean = String(text || '').trim()
      if (!clean) return ''
      return this.enqueue(async () => {
        await this.ensureConnected()
        this.send({
          type: 'conversation.item.create',
          item: {
            type: 'message',
            role: 'user',
            content: [
              {
                type: 'input_text',
                text:
                  language() === 'en'
                    ? `Read the following final answer exactly. Do not add, remove, summarize, or paraphrase anything:\n${clean}`
                    : `请逐字朗读下面的最终答复。不得增加、删除、总结或改写任何内容：\n${clean}`,
              },
            ],
          },
        })
        const spoken = await this.createAudioResponse(
          language() === 'en'
            ? 'Read the supplied final answer exactly, in a warm professional consultant voice.'
            : '严格逐字朗读刚才提供的最终答复，使用自然、亲切、专业的中文顾问语气。',
          'exact_backend_answer',
        )
        this.lastSpokenText = clean
        return spoken || clean
      })
    }

    async respondDirect(userText, instruction) {
      const clean = String(userText || '').trim()
      return this.enqueue(async () => {
        await this.ensureConnected()
        const prompt = [
          language() === 'en'
            ? 'You are Xiao Mu, the voice consultant at Senjing Flooring Living Gallery.'
            : '你是森境地板生活馆的语音顾问“小木”。',
          instruction || '',
          language() === 'en'
            ? `The user's normalized utterance is: ${clean}`
            : `用户最终确认的话是：${clean}`,
          language() === 'en'
            ? 'Answer the user now. Keep the response short and natural.'
            : '现在直接回答用户，保持简短自然。',
        ]
          .filter(Boolean)
          .join('\n')
        const spoken = await this.createAudioResponse(prompt, 'realtime_direct')
        this.lastSpokenText = spoken
        return spoken
      })
    }

    async stopOutput() {
      if (this.dc && this.dc.readyState === 'open') {
        this.send({ type: 'response.cancel' })
        this.send({ type: 'output_audio_buffer.clear' })
      }
      if (this.remoteAudio) {
        this.remoteAudio.pause()
      }
      this.outputStarted = false
      window.dispatchEvent(new CustomEvent('woodfloor:realtime-speaking-stop'))
    }

    status() {
      return {
        connected: this.pc?.connectionState === 'connected',
        data_channel: this.dc?.readyState || 'closed',
        output_mode: localStorage.getItem(VOICE_OUTPUT_KEY) || REALTIME_OUTPUT,
        last_route: this.lastRoute,
        last_latency: this.lastLatency,
      }
    }

    enqueue(operation) {
      const next = this.operationQueue.then(operation, operation)
      this.operationQueue = next.catch(() => undefined)
      return next
    }

    async ensureConnected() {
      if (
        this.pc &&
        this.dc &&
        this.dc.readyState === 'open' &&
        ['connected', 'connecting', 'new'].includes(this.pc.connectionState)
      ) {
        if (this.remoteAudio?.paused) await this.remoteAudio.play().catch(() => undefined)
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

    async connect() {
      await this.shutdownConnection()
      const statusResponse = await nativeFetch(`${API_BASE_URL}/api/realtime/status`, {
        headers: { Accept: 'application/json' },
      })
      if (!statusResponse.ok) throw new Error(`Realtime status failed: ${statusResponse.status}`)
      const status = await statusResponse.json()
      if (!status.configured || !status.enabled) throw new Error('GPT Realtime is not configured.')

      this.createSilentTrack()
      const pc = new RTCPeerConnection()
      const dc = pc.createDataChannel('oai-events')
      this.pc = pc
      this.dc = dc
      this.sender = pc.addTrack(this.silentTrack, this.silentStream)

      const remoteAudio = document.createElement('audio')
      remoteAudio.autoplay = true
      remoteAudio.playsInline = true
      remoteAudio.setAttribute('aria-hidden', 'true')
      remoteAudio.style.display = 'none'
      document.body.appendChild(remoteAudio)
      this.remoteAudio = remoteAudio

      pc.addEventListener('track', (event) => {
        remoteAudio.srcObject = event.streams[0] || new MediaStream([event.track])
        remoteAudio.play().catch(() => undefined)
      })
      dc.addEventListener('message', (event) => this.handleServerEvent(event))
      pc.addEventListener('connectionstatechange', () => {
        if (['failed', 'closed'].includes(pc.connectionState)) {
          this.rejectPending(new Error('GPT Realtime WebRTC connection was lost.'))
        }
      })

      const offer = await pc.createOffer()
      await pc.setLocalDescription(offer)
      const sdp = pc.localDescription?.sdp || offer.sdp
      const sessionResponse = await nativeFetch(
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
            language() === 'en'
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

    createSilentTrack() {
      if (this.silentTrack && this.silentStream) return
      const AudioContextClass = window.AudioContext || window.webkitAudioContext
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
      this.silentTrack = destination.stream.getAudioTracks()[0]
    }

    async restoreSilentTrack() {
      if (this.sender && this.silentTrack) {
        await this.sender.replaceTrack(this.silentTrack)
      }
      for (const track of this.microphoneStream?.getTracks() || []) track.stop()
      this.microphoneStream = null
      this.microphoneTrack = null
    }

    commitAudio() {
      return new Promise((resolve, reject) => {
        const timer = window.setTimeout(() => {
          if (this.pendingCommit?.reject === reject) this.pendingCommit = null
          reject(new Error('GPT Realtime did not confirm the audio buffer.'))
        }, COMMIT_TIMEOUT_MS)
        this.pendingCommit = {
          resolve: () => {
            clearTimeout(timer)
            this.pendingCommit = null
            resolve()
          },
          reject: (error) => {
            clearTimeout(timer)
            this.pendingCommit = null
            reject(error)
          },
        }
        this.send({ type: 'input_audio_buffer.commit' })
      })
    }

    createTextResponse(instructions, purpose) {
      return this.createResponse({
        modalities: ['text'],
        instructions,
        purpose,
      })
    }

    createAudioResponse(instructions, purpose) {
      return this.createResponse({
        modalities: ['audio'],
        instructions,
        purpose,
      })
    }

    createResponse({ modalities, instructions, purpose }) {
      return new Promise((resolve, reject) => {
        if (this.pendingResponse) {
          reject(new Error('Another GPT Realtime response is still active.'))
          return
        }
        const requestId = `${purpose}-${Date.now()}-${Math.random().toString(16).slice(2)}`
        const startedAt = performance.now()
        const timer = window.setTimeout(() => {
          if (this.pendingResponse?.requestId !== requestId) return
          this.send({ type: 'response.cancel' })
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

    maybeResolveResponse() {
      const pending = this.pendingResponse
      if (!pending || !pending.responseDone || !pending.audioStopped) return
      clearTimeout(pending.timer)
      this.pendingResponse = null
      const text = (pending.transcript || pending.text || '').trim()
      this.lastLatency = {
        purpose: pending.purpose,
        response_ms: Math.round(performance.now() - pending.startedAt),
      }
      pending.resolve(text)
    }

    handleServerEvent(message) {
      let event
      try {
        event = JSON.parse(message.data)
      } catch {
        return
      }

      if (event.type === 'input_audio_buffer.committed') {
        this.pendingCommit?.resolve()
        return
      }
      if (event.type === 'response.output_text.delta' && this.pendingResponse) {
        this.pendingResponse.text += event.delta || ''
        return
      }
      if (event.type === 'response.output_text.done' && this.pendingResponse) {
        this.pendingResponse.text = event.text || this.pendingResponse.text
        return
      }
      if (event.type === 'response.output_audio_transcript.delta' && this.pendingResponse) {
        this.pendingResponse.transcript += event.delta || ''
        return
      }
      if (event.type === 'response.output_audio_transcript.done' && this.pendingResponse) {
        this.pendingResponse.transcript = event.transcript || this.pendingResponse.transcript
        return
      }
      if (event.type === 'output_audio_buffer.started') {
        this.outputStarted = true
        window.dispatchEvent(new CustomEvent('woodfloor:realtime-speaking-start'))
        return
      }
      if (event.type === 'output_audio_buffer.stopped') {
        this.outputStarted = false
        if (this.pendingResponse) this.pendingResponse.audioStopped = true
        window.dispatchEvent(new CustomEvent('woodfloor:realtime-speaking-stop'))
        this.maybeResolveResponse()
        return
      }
      if (event.type === 'response.done') {
        const pending = this.pendingResponse
        if (!pending) return
        const responseRequestId = event.response?.metadata?.request_id
        if (responseRequestId && responseRequestId !== pending.requestId) return
        if (event.response?.status === 'failed') {
          const detail = event.response?.status_details?.error?.message || 'GPT Realtime response failed.'
          clearTimeout(pending.timer)
          this.pendingResponse = null
          pending.reject(new Error(detail))
          return
        }
        pending.responseDone = true
        this.maybeResolveResponse()
        return
      }
      if (event.type === 'error') {
        const code = event.error?.code || ''
        if (['response_cancel_not_active', 'input_audio_buffer_clear_empty'].includes(code)) return
        const error = new Error(event.error?.message || 'GPT Realtime returned an unknown error.')
        if (this.pendingCommit) this.pendingCommit.reject(error)
        else if (this.pendingResponse) {
          const pending = this.pendingResponse
          clearTimeout(pending.timer)
          this.pendingResponse = null
          pending.reject(error)
        }
      }
    }

    transcriptionInstructions() {
      return `
You are a speech-understanding layer, not a conversational assistant.
Return only the user's final intended utterance as plain text. Do not answer.
Language: ${language() === 'en' ? 'English' : 'Chinese Mandarin'}.
Later explicit corrections override earlier uncertain words.
Chinese correction signals such as “不”, “不是”, “不对”, “我是说”, “应该是” and character explanations are authoritative.
Example: “我喜欢钱会色，不，浅灰色，深浅的浅，灰色的灰” becomes “我喜欢浅灰色”.
Relevant terms include 浅灰色、深灰色、原木色、深胡桃色、SPC、多层实木、强化地板、防水、耐磨、地暖、宠物、客厅、卧室、全屋.
Never invent a preference. If genuinely unintelligible, output exactly __UNCLEAR__.
Output only normalized plain text without labels, JSON, Markdown, or quotation marks.
`.trim()
    }

    send(event) {
      if (!this.dc || this.dc.readyState !== 'open') throw new Error('GPT Realtime data channel is not open.')
      this.dc.send(JSON.stringify(event))
    }

    waitForDataChannel(channel) {
      if (channel.readyState === 'open') return Promise.resolve()
      return new Promise((resolve, reject) => {
        const timer = window.setTimeout(() => {
          cleanup()
          reject(new Error('Timed out while opening GPT Realtime data channel.'))
        }, CONNECTION_TIMEOUT_MS)
        const cleanup = () => {
          clearTimeout(timer)
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

    rejectPending(error) {
      if (this.pendingCommit) this.pendingCommit.reject(error)
      if (this.pendingResponse) {
        const pending = this.pendingResponse
        clearTimeout(pending.timer)
        this.pendingResponse = null
        pending.reject(error)
      }
    }

    async shutdownConnection() {
      this.rejectPending(new Error('GPT Realtime connection reset.'))
      await this.restoreSilentTrack().catch(() => undefined)
      this.dc?.close()
      this.pc?.close()
      this.remoteAudio?.remove()
      this.dc = null
      this.pc = null
      this.sender = null
      this.remoteAudio = null
      this.outputStarted = false
    }
  }

  const agent = new RealtimeAgentRuntime()
  window.__WOODFLOOR_REALTIME_AGENT__ = agent

  let lastChatPayload = null
  let lastAnswer = ''
  let skipNextTtsText = ''

  async function routeChat(input, init, body) {
    const startedAt = performance.now()
    const routeResponse = await nativeFetch(`${API_BASE_URL}/api/interaction/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify(body),
    })
    if (!routeResponse.ok) {
      const detail = await routeResponse.text().catch(() => '')
      throw new Error(`Interaction route failed: ${routeResponse.status} ${detail}`)
    }
    const payload = await routeResponse.json()
    agent.lastRoute = payload.response_route || 'terra'

    if (payload.response_route === 'repeat_last') {
      payload.answer = lastAnswer || (language() === 'en' ? 'There is no previous answer to repeat yet.' : '目前还没有上一条答复可以重复。')
    } else if (payload.response_route === 'realtime_direct') {
      const answer = await agent.respondDirect(body.text, payload.realtime_instruction)
      payload.answer = answer || (language() === 'en' ? 'I heard you.' : '我听到了。')
      skipNextTtsText = payload.answer.trim()
    } else if (payload.response_route === 'stop_speaking') {
      await agent.stopOutput()
    }

    if (payload.answer?.trim()) lastAnswer = payload.answer.trim()
    lastChatPayload = payload
    agent.lastLatency = {
      ...(agent.lastLatency || {}),
      route: payload.response_route,
      stop_to_chat_response_ms: Math.round(performance.now() - startedAt),
    }
    console.info('[voice-route]', {
      route: payload.response_route,
      intent: payload.route_intent,
      reason: payload.route_reason,
      latency_ms: Math.round(performance.now() - startedAt),
    })
    return jsonResponse(payload)
  }

  window.fetch = async (input, init) => {
    const url = requestUrl(input)
    const body = parseBody(init)

    if (url.includes('/api/chat') && body && typeof body.text === 'string') {
      try {
        return await routeChat(input, init, body)
      } catch (error) {
        console.warn('Routed interaction failed; using legacy /api/chat:', error)
        return nativeFetch(input, init)
      }
    }

    if (url.includes('/api/tts') && body && typeof body.text === 'string') {
      const mode = localStorage.getItem(VOICE_OUTPUT_KEY) || REALTIME_OUTPUT
      if (mode === REALTIME_OUTPUT) {
        const text = body.text.trim()
        if (skipNextTtsText && text === skipNextTtsText) {
          skipNextTtsText = ''
          return silentWavResponse()
        }
        try {
          await agent.speakExact(text)
          return silentWavResponse()
        } catch (error) {
          console.warn('GPT Realtime audio output failed; falling back to Kokoro chain:', error)
          const headers = new Headers(init?.headers)
          headers.set('Content-Type', 'application/json; charset=utf-8')
          return nativeFetch(input, {
            ...init,
            headers,
            body: JSON.stringify({ ...body, provider: 'local' }),
          })
        }
      }
    }

    return nativeFetch(input, init)
  }

  function installVoiceOutputControl() {
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
    title.textContent = language() === 'en' ? 'Voice' : '语音输出'
    const select = document.createElement('select')
    select.style.cssText = 'border:0;background:transparent;color:#5f4335;font:inherit;outline:none'
    const realtimeOption = document.createElement('option')
    realtimeOption.value = REALTIME_OUTPUT
    realtimeOption.textContent = language() === 'en' ? 'GPT Realtime (default)' : 'GPT Realtime（默认）'
    const kokoroOption = document.createElement('option')
    kokoroOption.value = KOKORO_OUTPUT
    kokoroOption.textContent = language() === 'en' ? 'Kokoro local voice' : 'Kokoro 本地语音'
    select.append(realtimeOption, kokoroOption)
    select.value = localStorage.getItem(VOICE_OUTPUT_KEY) || REALTIME_OUTPUT
    select.addEventListener('change', () => {
      localStorage.setItem(VOICE_OUTPUT_KEY, select.value)
      if (select.value === KOKORO_OUTPUT) agent.stopOutput().catch(() => undefined)
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
    if (localStorage.getItem(VOICE_OUTPUT_KEY) === REALTIME_OUTPUT) {
      agent.prewarm().catch((error) => console.warn('Realtime prewarm deferred:', error))
    }
  }, 500)
})()
