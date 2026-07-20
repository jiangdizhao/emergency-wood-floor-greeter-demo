const VOICE_OUTPUT_KEY = 'woodfloor_voice_output'
const OPENAI_MODE = 'openai'
const OPENAI_VOICE = 'marin'

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

const previousFetch = window.fetch.bind(window)

window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  if (
    !requestUrl(input).includes('/api/tts') ||
    localStorage.getItem(VOICE_OUTPUT_KEY) !== OPENAI_MODE
  ) {
    return await previousFetch(input, init)
  }

  const body = parseBody(init)
  if (!body || typeof body.text !== 'string') return await previousFetch(input, init)

  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json; charset=utf-8')
  return await previousFetch(input, {
    ...init,
    headers,
    body: JSON.stringify({ ...body, provider: 'openai', voice: OPENAI_VOICE }),
  })
}
