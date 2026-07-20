import { getRealtimeAgentRuntime } from './realtimeAgentRuntime'

export type VoiceOutputMode = 'realtime' | 'kokoro' | 'openai'

const VOICE_OUTPUT_KEY = 'woodfloor_voice_output'
const REALTIME_MODE: VoiceOutputMode = 'realtime'
const KOKORO_MODE: VoiceOutputMode = 'kokoro'
const OPENAI_MODE: VoiceOutputMode = 'openai'
const ACK_DURATION_MS = 80
const SAMPLE_RATE = 16_000
const CHANNELS = 1
const BITS_PER_SAMPLE = 16
const DUPLICATE_SUPPRESSION_MS = 15_000
const CONTROL_ID = 'woodfloor-voice-output-control'
const STATUS_ID = 'woodfloor-voice-output-state'

const agent = getRealtimeAgentRuntime()
const previousFetch = window.fetch.bind(window)
let activeMedia: HTMLMediaElement | null = null
let outputGeneration = 0
let recentText = ''
let recentTextAt = 0
let recentResult: 'played' | 'failed' | null = null

function selectedLanguage(): 'zh' | 'en' {
  const configured = (window as Window & { __WOODFLOOR_LANGUAGE__?: string }).__WOODFLOOR_LANGUAGE__
  return configured === 'en' || localStorage.getItem('woodfloor_ui_language') === 'en' ? 'en' : 'zh'
}

export function getVoiceOutputMode(): VoiceOutputMode {
  const stored = localStorage.getItem(VOICE_OUTPUT_KEY)
  if (stored === KOKORO_MODE || stored === OPENAI_MODE || stored === REALTIME_MODE) return stored
  localStorage.setItem(VOICE_OUTPUT_KEY, REALTIME_MODE)
  return REALTIME_MODE
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

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index))
  }
}

function createPlayableSilenceWav(): ArrayBuffer {
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
  return buffer
}

function acknowledgementResponse(provider: string, errorMessage?: string): Response {
  const headers = new Headers({
    'Content-Type': 'audio/wav',
    'Cache-Control': 'no-store',
    'X-TTS-Provider': provider,
    'X-Woodfloor-Strict-Voice-Mode': '1',
  })
  if (errorMessage) headers.set('X-Woodfloor-Voice-Error', encodeURIComponent(errorMessage))
  return new Response(createPlayableSilenceWav(), { status: 200, headers })
}

function modeLabel(mode: VoiceOutputMode): string {
  if (selectedLanguage() === 'en') {
    if (mode === KOKORO_MODE) return 'Kokoro local voice'
    if (mode === OPENAI_MODE) return 'OpenAI TTS'
    return 'GPT Realtime 2'
  }
  if (mode === KOKORO_MODE) return 'Kokoro 本地语音'
  if (mode === OPENAI_MODE) return 'OpenAI TTS'
  return 'GPT Realtime 2'
}

function setStatus(message: string, isError = false): void {
  const state = document.getElementById(STATUS_ID)
  if (state) {
    state.textContent = message
    state.style.color = isError ? '#b13f2e' : '#6c8b71'
  }
  window.dispatchEvent(
    new CustomEvent('woodfloor:voice-output-status', {
      detail: { message, error: isError, mode: getVoiceOutputMode() },
    }),
  )
}

function markResult(text: string, result: 'played' | 'failed'): void {
  recentText = text.trim()
  recentTextAt = Date.now()
  recentResult = result
}

function isRecentDuplicate(text: string): boolean {
  return Boolean(
    recentText &&
      text.trim() === recentText &&
      Date.now() - recentTextAt <= DUPLICATE_SUPPRESSION_MS,
  )
}

async function stopAllOutput(): Promise<void> {
  outputGeneration += 1
  await agent.stopOutput().catch(() => undefined)
  if (activeMedia) {
    activeMedia.pause()
    activeMedia.currentTime = 0
    activeMedia = null
  }
  for (const media of Array.from(document.querySelectorAll<HTMLMediaElement>('audio, video'))) {
    media.pause()
  }
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

window.addEventListener('woodfloor:voice-output-played', (event) => {
  const detail = (event as CustomEvent<{ text?: string }>).detail
  if (detail?.text) markResult(detail.text, 'played')
})

window.addEventListener('woodfloor:voice-output-stop', () => {
  void stopAllOutput()
})

function installSingleMediaOwner(): void {
  const prototype = HTMLMediaElement.prototype as HTMLMediaElement & {
    __woodfloorOriginalPlay?: typeof HTMLMediaElement.prototype.play
  }
  if (prototype.__woodfloorOriginalPlay) return
  const originalPlay = HTMLMediaElement.prototype.play
  Object.defineProperty(prototype, '__woodfloorOriginalPlay', {
    value: originalPlay,
    configurable: false,
    enumerable: false,
    writable: false,
  })
  HTMLMediaElement.prototype.play = function playSingleOwner(): Promise<void> {
    if (activeMedia && activeMedia !== this) {
      activeMedia.pause()
      activeMedia.currentTime = 0
    }
    activeMedia = this
    const cleanup = () => {
      if (activeMedia === this) activeMedia = null
    }
    this.addEventListener('ended', cleanup, { once: true })
    this.addEventListener('error', cleanup, { once: true })
    return originalPlay.call(this)
  }
}

function disableBrowserSpeechFallback(): void {
  if (!('speechSynthesis' in window)) return
  const synthesis = window.speechSynthesis as SpeechSynthesis & { __woodfloorStrictSpeak?: boolean }
  if (synthesis.__woodfloorStrictSpeak) return
  Object.defineProperty(synthesis, '__woodfloorStrictSpeak', {
    value: true,
    configurable: false,
    enumerable: false,
    writable: false,
  })
  Object.defineProperty(synthesis, 'speak', {
    configurable: true,
    value: (utterance: SpeechSynthesisUtterance) => {
      console.warn('Browser TTS fallback is disabled in the office branch.')
      window.setTimeout(() => {
        utterance.onerror?.(new Event('error') as unknown as SpeechSynthesisErrorEvent)
      }, 0)
    },
  })
}

function ensureVoiceControl(): void {
  const control = document.getElementById(CONTROL_ID)
  const select = control?.querySelector<HTMLSelectElement>('select')
  if (!control || !select) return

  select.innerHTML = ''
  const options: Array<{ value: VoiceOutputMode; zh: string; en: string }> = [
    { value: REALTIME_MODE, zh: 'GPT Realtime 2（默认）', en: 'GPT Realtime 2 (default)' },
    { value: KOKORO_MODE, zh: 'Kokoro 本地语音', en: 'Kokoro local voice' },
    { value: OPENAI_MODE, zh: 'OpenAI TTS', en: 'OpenAI TTS' },
  ]
  for (const option of options) {
    const node = document.createElement('option')
    node.value = option.value
    node.textContent = selectedLanguage() === 'en' ? option.en : option.zh
    select.appendChild(node)
  }
  select.value = getVoiceOutputMode()

  if (!select.dataset.strictVoiceBound) {
    select.dataset.strictVoiceBound = '1'
    select.addEventListener('change', () => {
      const next = select.value as VoiceOutputMode
      if (![REALTIME_MODE, KOKORO_MODE, OPENAI_MODE].includes(next)) return
      localStorage.setItem(VOICE_OUTPUT_KEY, next)
      void stopAllOutput()
      setStatus(
        selectedLanguage() === 'en'
          ? `${modeLabel(next)} selected. Automatic voice fallback is disabled.`
          : `已选择 ${modeLabel(next)}。不会自动切换到其他发音人。`,
      )
      window.dispatchEvent(new CustomEvent('woodfloor:voice-output-changed', { detail: next }))
    })
  }

  let state = document.getElementById(STATUS_ID)
  if (!state) {
    state = document.createElement('span')
    state.id = STATUS_ID
    state.style.cssText = 'max-width:210px;font-size:11px;font-weight:650;line-height:1.25;color:#6c8b71'
    control.appendChild(state)
  }
  state.textContent =
    selectedLanguage() === 'en'
      ? `${modeLabel(getVoiceOutputMode())}; no automatic fallback`
      : `${modeLabel(getVoiceOutputMode())}；不自动切换`
}

function installVoiceControlObserver(): void {
  ensureVoiceControl()
  const observer = new MutationObserver(() => ensureVoiceControl())
  observer.observe(document.body, { childList: true, subtree: true })
}

window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const url = requestUrl(input)
  const body = parseJsonBody(init)
  if (!url.includes('/api/tts') || typeof body?.text !== 'string') {
    return await previousFetch(input, init)
  }

  const text = String(body.text).trim()
  const mode = getVoiceOutputMode()
  const requestGeneration = ++outputGeneration

  if (!text) return acknowledgementResponse(mode)

  if (isRecentDuplicate(text)) {
    return acknowledgementResponse(
      mode === REALTIME_MODE ? 'gpt-realtime' : mode === KOKORO_MODE ? 'local-kokoro' : 'openai',
      recentResult === 'failed' ? 'Previous attempt failed; duplicate fallback suppressed.' : undefined,
    )
  }

  if (mode === REALTIME_MODE) {
    await stopAllOutput()
    try {
      await agent.speakExact(text)
      if (requestGeneration !== outputGeneration) return acknowledgementResponse('gpt-realtime')
      markResult(text, 'played')
      setStatus(selectedLanguage() === 'en' ? 'GPT Realtime 2 playback completed.' : 'GPT Realtime 2 播放完成。')
      return acknowledgementResponse('gpt-realtime')
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      markResult(text, 'failed')
      setStatus(
        selectedLanguage() === 'en'
          ? `GPT Realtime 2 failed. Text remains visible; no fallback was used.`
          : `GPT Realtime 2 播放失败。文字已保留，未自动切换发音人。`,
        true,
      )
      console.error('Strict GPT Realtime output failed:', message)
      return acknowledgementResponse('gpt-realtime', message)
    }
  }

  const provider = mode === KOKORO_MODE ? 'local' : 'openai'
  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json; charset=utf-8')
  const rewrittenInit: RequestInit = {
    ...init,
    headers,
    body: JSON.stringify({ ...body, provider }),
  }

  const response = await previousFetch(input, rewrittenInit).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error)
    return new Response(message, { status: 599, statusText: 'Voice provider request failed' })
  })

  if (!response.ok) {
    const detail = await response.clone().text().catch(() => '')
    const message = `${modeLabel(mode)} unavailable${detail ? `: ${detail}` : ''}`
    markResult(text, 'failed')
    setStatus(
      selectedLanguage() === 'en'
        ? `${modeLabel(mode)} failed. Text remains visible; no fallback was used.`
        : `${modeLabel(mode)} 播放失败。文字已保留，未自动切换发音人。`,
      true,
    )
    console.error(message)
    return acknowledgementResponse(mode === KOKORO_MODE ? 'local-kokoro' : 'openai', message)
  }

  if (requestGeneration !== outputGeneration) {
    return acknowledgementResponse(mode === KOKORO_MODE ? 'local-kokoro' : 'openai')
  }

  markResult(text, 'played')
  setStatus(
    selectedLanguage() === 'en'
      ? `${modeLabel(mode)} audio is ready.`
      : `${modeLabel(mode)} 音频已就绪。`,
  )
  return response
}

installSingleMediaOwner()
disableBrowserSpeechFallback()

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', installVoiceControlObserver, { once: true })
} else {
  installVoiceControlObserver()
}

export async function stopVoiceOutput(): Promise<void> {
  await stopAllOutput()
}
