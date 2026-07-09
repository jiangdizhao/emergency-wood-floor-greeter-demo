export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000'

export type SessionState =
  | 'IDLE'
  | 'PERSON_DETECTED_FAR'
  | 'PERSON_CLOSE_WAITING_GREETING'
  | 'GREETING_RECEIVED'
  | 'INTRODUCING_PRODUCTS'
  | 'CONVERSATION_ACTIVE'
  | 'SESSION_END'

export type ResponseLanguage = 'zh' | 'en'
export type TTSProvider = 'auto' | 'openai' | 'browser'

export type FlooringProduct = {
  id: string
  name: string
  type: string
  color: string
  style: string[]
  suitable_rooms: string[]
  waterproof: boolean
  floor_heating: boolean
  pet_friendly: boolean
  child_friendly: boolean
  wear_level: string
  price_range: string
  spec: string
  selling_points: string[]
}

export type CustomerProfile = {
  session_id: string
  customer_name: string | null
  phone: string | null
  room_type: string | null
  style: string | null
  budget: string | null
  special_needs: string[]
  concerns: string[]
  recommended_product_ids: string[]
  conversation_summary: string
  follow_up_status: string
  follow_up_suggestion: string
}

export type VisionStatus = {
  ok: boolean
  running: boolean
  camera_opened: boolean
  person_detected: boolean
  distance: string
  face_height_ratio: number
  face_area_ratio: number
  face_close_votes: number
  face_window_size: number
  stable_close: boolean
  wave_detected: boolean
  raw_wave_event?: string | null
  raw_wave_ignored_reason?: string | null
  greeting_recent?: boolean
  last_wave_event: string | null
  last_wave_at: number | null
  state: SessionState
  error: string | null
  fps_estimate: number
  wave_debug: Record<string, unknown>
}

export type ChatResponse = {
  answer: string
  recommended_products: FlooringProduct[]
  customer_profile: CustomerProfile
  follow_up_suggestion: string
  state: SessionState
}

export type SessionStatusResponse = {
  state: SessionState
  status: Record<string, unknown>
  customer_profile: CustomerProfile
}

export type CompareRow = {
  field: string
  values: Record<string, unknown>
}

export type TTSStatus = {
  ok: boolean
  openai_tts_configured: boolean
  model: string
  voice: string
  fallback: string
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json; charset=utf-8')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`${response.status} ${response.statusText}${text ? `: ${text}` : ''}`)
  }

  return (await response.json()) as T
}

export function streamUrl(): string {
  return `${API_BASE_URL}/api/vision/stream?ts=${Date.now()}`
}

export function getVisionStatus(): Promise<VisionStatus> {
  return requestJson<VisionStatus>('/api/vision/status')
}

export function startVision(): Promise<{ ok: boolean; message: string; status: VisionStatus }> {
  return requestJson('/api/vision/start', { method: 'POST' })
}

export function stopVision(): Promise<{ ok: boolean; message: string; status: VisionStatus }> {
  return requestJson('/api/vision/stop', { method: 'POST' })
}

export function getProducts(): Promise<{ products: FlooringProduct[] }> {
  return requestJson('/api/products')
}

export function getSessionStatus(): Promise<SessionStatusResponse> {
  return requestJson('/api/session/status')
}

export function resetSession(): Promise<SessionStatusResponse> {
  return requestJson('/api/session/reset', { method: 'POST' })
}

export function sendDemoEvent(event: string): Promise<SessionStatusResponse> {
  return requestJson('/api/demo/event', {
    method: 'POST',
    body: JSON.stringify({ event }),
  })
}

export function sendVoiceGreeting(text = '你好'): Promise<{
  accepted: boolean
  state: SessionState
  message: string
  status: Record<string, unknown>
}> {
  return requestJson('/api/greeting/voice', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

export function sendChat(text: string, responseLanguage?: ResponseLanguage): Promise<ChatResponse> {
  return requestJson('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ text, response_language: responseLanguage }),
  })
}

export function getTTSStatus(): Promise<TTSStatus> {
  return requestJson<TTSStatus>('/api/tts/status')
}

export async function synthesizeSpeech(
  text: string,
  language: ResponseLanguage,
  provider: TTSProvider = 'auto',
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/tts`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
    },
    body: JSON.stringify({ text, language, provider }),
  })

  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ''}`)
  }

  return await response.blob()
}

export function compareProducts(productIds: string[]): Promise<{ comparison: CompareRow[] }> {
  return requestJson('/api/products/compare', {
    method: 'POST',
    body: JSON.stringify({ product_ids: productIds }),
  })
}
