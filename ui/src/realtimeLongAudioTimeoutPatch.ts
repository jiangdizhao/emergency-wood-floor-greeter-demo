import { getRealtimeAgentRuntime, type RealtimeAgentRuntime } from './realtimeAgentRuntime'

const TEXT_RESPONSE_TIMEOUT_MS = 30_000
const AUDIO_START_TIMEOUT_MS = 15_000
const MIN_AUDIO_COMPLETION_TIMEOUT_MS = 90_000
const MAX_AUDIO_COMPLETION_TIMEOUT_MS = 360_000
const AUDIO_BASE_MARGIN_MS = 45_000
const CJK_CHARACTER_MS = 520
const LATIN_WORD_MS = 420

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
  audioStarted?: boolean
  audioCompletionTimeoutMs?: number
}

type RuntimeInternals = RealtimeAgentRuntime & {
  pendingResponse: PendingResponse | null
  createResponse: (
    modalities: Array<'text' | 'audio'>,
    instructions: string,
    purpose: string,
  ) => Promise<string>
  handleServerEvent: (message: MessageEvent<string>) => void
  send: (event: Record<string, unknown>) => void
  safeSend: (event: Record<string, unknown>) => void
}

type RealtimeServerEvent = {
  type?: string
  response?: {
    metadata?: Record<string, unknown>
  }
}

function estimateAudioCompletionTimeoutMs(instructions: string): number {
  const cjkCharacters = instructions.match(/[\u3400-\u9fff]/g)?.length ?? 0
  const latinWords = instructions.match(/[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*/g)?.length ?? 0
  const estimatedSpeechMs = cjkCharacters * CJK_CHARACTER_MS + latinWords * LATIN_WORD_MS
  return Math.min(
    MAX_AUDIO_COMPLETION_TIMEOUT_MS,
    Math.max(MIN_AUDIO_COMPLETION_TIMEOUT_MS, estimatedSpeechMs + AUDIO_BASE_MARGIN_MS),
  )
}

function parseEvent(message: MessageEvent<string>): RealtimeServerEvent | null {
  try {
    return JSON.parse(message.data) as RealtimeServerEvent
  } catch {
    return null
  }
}

function installLongAudioTimeoutPatch(): void {
  const runtime = getRealtimeAgentRuntime() as RuntimeInternals
  const originalHandleServerEvent = runtime.handleServerEvent.bind(runtime)

  function rejectTimedOutResponse(
    pending: PendingResponse,
    message: string,
  ): void {
    if (runtime.pendingResponse?.requestId !== pending.requestId) return
    runtime.safeSend({ type: 'response.cancel' })
    runtime.pendingResponse = null
    pending.reject(new Error(message))
  }

  runtime.createResponse = function createResponseWithAudioAwareTimeout(
    modalities: Array<'text' | 'audio'>,
    instructions: string,
    purpose: string,
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      if (runtime.pendingResponse) {
        reject(new Error('Another GPT Realtime response is still active.'))
        return
      }

      const requestId = `${purpose}-${Date.now()}-${Math.random().toString(16).slice(2)}`
      const startedAt = performance.now()
      const hasAudio = modalities.includes('audio')
      const audioCompletionTimeoutMs = hasAudio
        ? estimateAudioCompletionTimeoutMs(instructions)
        : undefined

      const pending = {
        requestId,
        purpose,
        modalities,
        text: '',
        transcript: '',
        responseDone: false,
        audioStopped: !hasAudio,
        startedAt,
        timer: 0,
        resolve,
        reject,
        audioStarted: false,
        audioCompletionTimeoutMs,
      } satisfies PendingResponse

      const initialTimeoutMs = hasAudio ? AUDIO_START_TIMEOUT_MS : TEXT_RESPONSE_TIMEOUT_MS
      pending.timer = window.setTimeout(() => {
        rejectTimedOutResponse(
          pending,
          hasAudio
            ? 'GPT Realtime audio did not start within 15 seconds.'
            : 'GPT Realtime text response timed out.',
        )
      }, initialTimeoutMs)

      runtime.pendingResponse = pending
      runtime.send({
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

  runtime.handleServerEvent = function handleServerEventWithAudioAwareTimeout(
    message: MessageEvent<string>,
  ): void {
    const event = parseEvent(message)
    const pending = runtime.pendingResponse

    if (
      event?.type === 'output_audio_buffer.started' &&
      pending?.modalities.includes('audio') &&
      !pending.audioStarted
    ) {
      pending.audioStarted = true
      window.clearTimeout(pending.timer)
      const completionTimeoutMs =
        pending.audioCompletionTimeoutMs ?? MIN_AUDIO_COMPLETION_TIMEOUT_MS
      pending.timer = window.setTimeout(() => {
        rejectTimedOutResponse(
          pending,
          `GPT Realtime audio did not finish within the ${Math.round(
            completionTimeoutMs / 1000,
          )}-second safety window.`,
        )
      }, completionTimeoutMs)
    }

    originalHandleServerEvent(message)
  }
}

installLongAudioTimeoutPatch()
