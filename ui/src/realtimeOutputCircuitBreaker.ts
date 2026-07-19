const VOICE_OUTPUT_KEY = 'woodfloor_voice_output'
const REALTIME_OUTPUT = 'realtime'
const KOKORO_OUTPUT = 'kokoro'
const CIRCUIT_KEY = 'woodfloor_realtime_output_disabled_until'
const CIRCUIT_DURATION_MS = 60_000

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.href
  return input.url
}

function circuitOpen(): boolean {
  const until = Number(window.sessionStorage.getItem(CIRCUIT_KEY) ?? 0)
  return Number.isFinite(until) && until > Date.now()
}

function openCircuit(reason: string): void {
  const until = Date.now() + CIRCUIT_DURATION_MS
  window.sessionStorage.setItem(CIRCUIT_KEY, String(until))
  window.dispatchEvent(
    new CustomEvent('woodfloor:realtime-output-fallback', {
      detail: { reason, until },
    }),
  )
  console.warn('GPT Realtime voice output paused for 60 seconds:', reason)
}

const previousFetch = window.fetch.bind(window)

window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const isTts = requestUrl(input).includes('/api/tts')
  const selectedMode = window.localStorage.getItem(VOICE_OUTPUT_KEY) ?? REALTIME_OUTPUT

  if (!isTts || selectedMode !== REALTIME_OUTPUT) {
    return await previousFetch(input, init)
  }

  if (circuitOpen()) {
    // The existing Realtime fetch adapter checks this preference synchronously.
    // Temporarily expose Kokoro mode for this request, then restore the user's
    // actual preference so Realtime can be retried after the circuit expires.
    window.localStorage.setItem(VOICE_OUTPUT_KEY, KOKORO_OUTPUT)
    try {
      return await previousFetch(input, init)
    } finally {
      if (window.localStorage.getItem(VOICE_OUTPUT_KEY) === KOKORO_OUTPUT) {
        window.localStorage.setItem(VOICE_OUTPUT_KEY, REALTIME_OUTPUT)
      }
    }
  }

  const response = await previousFetch(input, init)
  const provider = response.headers.get('x-tts-provider')?.toLowerCase() ?? ''
  if (!response.ok) {
    openCircuit(`TTS HTTP ${response.status}`)
  } else if (provider && provider !== 'gpt-realtime') {
    openCircuit(`Realtime output fell back to ${provider}`)
  }
  return response
}
