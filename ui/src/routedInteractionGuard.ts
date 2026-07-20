import { getRealtimeAgentRuntime, type RealtimeAgentRuntime } from './realtimeAgentRuntime'
import { getVoiceOutputMode } from './voiceOutputManager'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000'

type RoutePayload = {
  answer?: string
  response_route?: string
  route_intent?: string
  route_reason?: string
  realtime_instruction?: string | null
  audio_already_played?: boolean
  [key: string]: unknown
}

type RealtimeTextInternals = RealtimeAgentRuntime & {
  ensureConnected: () => Promise<void>
  createResponse: (
    modalities: Array<'text' | 'audio'>,
    instructions: string,
    purpose: string,
  ) => Promise<string>
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

function selectedLanguage(): 'zh' | 'en' {
  const configured = (window as Window & { __WOODFLOOR_LANGUAGE__?: string }).__WOODFLOOR_LANGUAGE__
  return configured === 'en' || localStorage.getItem('woodfloor_ui_language') === 'en' ? 'en' : 'zh'
}

function directPrompt(userText: string, instruction?: string | null): string {
  return [
    selectedLanguage() === 'en'
      ? 'You are Xiao Mu, the voice consultant at Senjing Flooring Living Gallery.'
      : '你是森境地板生活馆的语音顾问“小木”。',
    instruction ?? '',
    selectedLanguage() === 'en'
      ? `The user's normalized utterance is: ${userText}`
      : `用户最终确认的话是：${userText}`,
    selectedLanguage() === 'en'
      ? 'Return only the final answer text in no more than two short sentences. Do not produce audio.'
      : '只返回最终回答文本，最多两句，保持简短自然。不要输出音频。',
  ]
    .filter(Boolean)
    .join('\n')
}

async function respondDirectText(
  runtime: RealtimeAgentRuntime,
  userText: string,
  instruction?: string | null,
): Promise<string> {
  const internals = runtime as RealtimeTextInternals
  if (typeof internals.ensureConnected !== 'function' || typeof internals.createResponse !== 'function') {
    throw new Error('GPT Realtime text response capability is unavailable.')
  }
  await internals.ensureConnected()
  return await internals.createResponse(
    ['text'],
    directPrompt(userText, instruction),
    'realtime_direct_text',
  )
}

const previousFetch = window.fetch.bind(window)
const agent = getRealtimeAgentRuntime()
let lastAnswer = ''
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
      // No spoken progress cue: the selected voice provider owns the entire turn.
      // The UI already displays its normal visual processing indicator while the
      // guarded Terra/Qwen execution is running.
      payload = await fetchRoute('route', body)
    } else if (route === 'repeat_last') {
      payload.answer =
        lastAnswer ||
        (selectedLanguage() === 'en'
          ? 'There is no previous answer to repeat yet.'
          : '目前还没有上一条答复可以重复。')
    } else if (route === 'realtime_direct') {
      const userText = String(body.text)
      if (getVoiceOutputMode() === 'realtime') {
        try {
          payload.answer = await agent.respondDirect(userText, payload.realtime_instruction)
        } catch (error) {
          const interrupted =
            listeningGeneration !== generationAtStart ||
            (error instanceof Error && error.name === 'AbortError')
          if (!interrupted) throw error
          payload.answer = ''
        }
        if (listeningGeneration !== generationAtStart) payload.answer = ''
        const answer = String(payload.answer ?? '').trim()
        if (answer) {
          payload.audio_already_played = true
          window.dispatchEvent(
            new CustomEvent('woodfloor:voice-output-played', {
              detail: { text: answer, provider: 'gpt-realtime' },
            }),
          )
        }
      } else {
        payload.answer = await respondDirectText(agent, userText, payload.realtime_instruction)
        payload.audio_already_played = false
      }
    } else if (route === 'stop_speaking') {
      window.dispatchEvent(new CustomEvent('woodfloor:voice-output-stop'))
      await agent.stopOutput()
    }

    const answer = String(payload.answer ?? '').trim()
    if (answer) lastAnswer = answer
    console.info('[voice-route]', {
      route,
      intent: payload.route_intent,
      reason: payload.route_reason,
      output_mode: getVoiceOutputMode(),
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
