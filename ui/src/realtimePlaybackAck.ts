const REALTIME_PROVIDER = 'gpt-realtime'
const ACK_DURATION_MS = 80
const SAMPLE_RATE = 16_000
const CHANNELS = 1
const BITS_PER_SAMPLE = 16

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  if (input instanceof URL) return input.href
  return input.url
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index))
  }
}

function createPlayableSilenceWav(): Uint8Array {
  const sampleCount = Math.max(1, Math.round((SAMPLE_RATE * ACK_DURATION_MS) / 1000))
  const bytesPerSample = BITS_PER_SAMPLE / 8
  const dataSize = sampleCount * CHANNELS * bytesPerSample
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)

  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, CHANNELS, true)
  view.setUint32(24, SAMPLE_RATE, true)
  view.setUint32(28, SAMPLE_RATE * CHANNELS * bytesPerSample, true)
  view.setUint16(32, CHANNELS * bytesPerSample, true)
  view.setUint16(34, BITS_PER_SAMPLE, true)
  writeAscii(view, 36, 'data')
  view.setUint32(40, dataSize, true)

  return new Uint8Array(buffer)
}

function playableRealtimeAck(original: Response): Response {
  const headers = new Headers(original.headers)
  headers.set('Content-Type', 'audio/wav')
  headers.set('Cache-Control', 'no-store')
  headers.set('X-TTS-Provider', REALTIME_PROVIDER)
  headers.set('X-Woodfloor-Audio-Already-Played', '1')
  headers.delete('Content-Length')
  return new Response(createPlayableSilenceWav(), {
    status: 200,
    statusText: 'OK',
    headers,
  })
}

const previousFetch = window.fetch.bind(window)

window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const response = await previousFetch(input, init)
  if (!requestUrl(input).includes('/api/tts')) return response

  const provider = response.headers.get('x-tts-provider')?.trim().toLowerCase() ?? ''
  if (response.ok && provider === REALTIME_PROVIDER) {
    // Realtime has already played the audible response over WebRTC. The legacy
    // React audio path still expects a playable Blob. Return a short valid silent
    // WAV acknowledgement so playAudioBlob resolves normally and does not trigger
    // Kokoro, Backend auto TTS, and finally browser speech synthesis for the same text.
    return playableRealtimeAck(response)
  }

  return response
}
