import { getRealtimeAgentRuntime } from './realtimeAgentRuntime'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000'
const VOICE_OUTPUT_KEY = 'woodfloor_voice_output'
const REALTIME_OUTPUT = 'realtime'

type RoutePayload = {
  answer?: string
  response_route?: string
  route_intent?: string
  route_reason?: string
  realtime_instruction?: string | null
  [key: string]: unknown
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.href
  return input.url
}

function parseBody(init?: RequestInit): Record<string, unknown> | null {
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

function selectedLanguage(): 'zh' | 'en' {
  const configured = (window as Window & { __WOODFLOOR_LANGUAGE__?: string }).__WOODFLOOR_LANGUAGE__
  return configured === 'en' || localStorage.getItem('woodfloor_ui_language') === 'en' ? 'en' : 'zh'
}

function kokoroSmalltalkFallback(text: string): string {
  const normalized = text.toLowerCase()
  if (selectedLanguage() === 'en') {
    if (normalized.includes('nice to meet')) return 'It is nice to meet you too. Please continue at your own pace.'
    if (normalized.includes('hear me')) return 'Yes, I can hear you. In a noisy venue, please stay close to the microphone and finish the sentence before releasing the button.'
    if (normalized.includes('sound')) return 'Thank you. I will keep my voice natural, clear, and concise.'
    return 'I am listening. Please continue.'
  }
  if (normalized.includes('见到你很高兴')) return '我也很高兴见到您。您可以按自己的节奏继续聊。'
  if (normalized.includes('听清') || normalized.includes('听见') || normalized.includes('吵') || normalized.includes('嘈杂')) {
    return '可以听到。展会环境较吵时，请靠近麦克风，并按住说话按钮完整说完。'
  }
  if (normalized.includes('说话')) return '谢谢，我会尽量保持自然、清楚，也会控制回答长度。'
  return '我在听，您可以继续说。'
}

function progressCue(): string {
  return selectedLanguage() === 'en'
    ? 'Okay, I am checking the relevant information now.'
    : '好的，我正在核对相关信息。'
}

const previousFetch = window.fetch.bind(window)
const agent = getRealtimeAgentRuntime()
let lastAnswer = ''
let skipNextTtsText = ''
let listeningGeneration = 0

window.addEventListener('woodfloor:realtime-listening-start', () => {
  listeningGeneration += 1
})

async function fetchRoute(path: 'classify' | 'route', body: Record<string, unknown>): Promise<RoutePayload> {
  const response = await previousFetch(`${API_BASE_URL}/api/interaction/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`Interaction ${path} failed: ${response.status} ${detail}`)
  }
  return (await response.json()) as RoutePayload
}

window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const url = requestUrl(input)
  const body = parseBody(init)

  if (url.includes('/api/tts') && typeof body?.text === 'string') {
    const text = String(body.text).trim()
    if (skipNextTtsText && text === skipNextTtsText) {
      skipNextTtsText = ''
      return silentWavResponse()
    }
    return await previousFetch(input, init)
  }

  if (!url.includes('/api/chat') || typeof body?.text !== 'string') {
    return await previousFetch(input, init)
  }

  const startedAt = performance.now()
  const generationAtStart = listeningGeneration
  try {
    let payload = await fetchRoute('classify', body)
    const classifyMs = Math.round(performance.now() - startedAt)
    const route = payload.response_route ?? 'terra'

    if (route === 'terra') {
      // Begin guarded business work immediately. While it runs, Realtime gives a
      // short progress cue so the visitor does not face several seconds of silence.
      const executionPromise = fetchRoute('route', body)
      if ((localStorage.getItem(VOICE_OUTPUT_KEY) ?? REALTIME_OUTPUT) === REALTIME_OUTPUT) {
        try {
          await agent.speakExact(progressCue())
        } catch (error) {
          const interrupted =
            listeningGeneration !== generationAtStart ||
            (error instanceof Error && error.name === 'AbortError')
          if (!interrupted) console.warn('Realtime progress cue could not play:', error)
        }
      }
      payload = await executionPromise
    } else if (route === 'repeat_last') {
      payload.answer =
        lastAnswer ||
        (selectedLanguage() === 'en'
          ? 'There is no previous answer to repeat yet.'
          : '目前还没有上一条答复可以重复。')
    } else if (route === 'realtime_direct') {
      if ((localStorage.getItem(VOICE_OUTPUT_KEY) ?? REALTIME_OUTPUT) === REALTIME_OUTPUT) {
        try {
          payload.answer = await agent.respondDirect(String(body.text), payload.realtime_instruction)
        } catch (error) {
          const interrupted =
            listeningGeneration !== generationAtStart ||
            (error instanceof Error && error.name === 'AbortError')
          if (!interrupted) throw error
          payload.answer = ''
        }
        if (listeningGeneration !== generationAtStart) payload.answer = ''
        const directAnswer = String(payload.answer ?? '').trim()
        if (directAnswer) skipNextTtsText = directAnswer
      } else {
        // The user explicitly selected Kokoro output. Keep Realtime as the input
        // understanding layer, but provide a safe short text for Kokoro to read.
        payload.answer = kokoroSmalltalkFallback(String(body.text))
      }
    } else if (route === 'stop_speaking') {
      await agent.stopOutput()
    }

    const answer = String(payload.answer ?? '').trim()
    if (answer) lastAnswer = answer
    console.info('[voice-route]', {
      route,
      intent: payload.route_intent,
      reason: payload.route_reason,
      classify_ms: classifyMs,
      total_ms: Math.round(performance.now() - startedAt),
    })
    return jsonResponse(payload)
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return jsonResponse({ answer: '', response_route: 'cancelled' })
    }
    console.warn('Authoritative interaction route failed; using the legacy chat path:', error)
    return await previousFetch(input, init)
  }
}
