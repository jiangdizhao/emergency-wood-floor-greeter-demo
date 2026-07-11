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
export type TTSProvider = 'auto' | 'local' | 'openai' | 'browser'
export type DialogueProvider = 'terra' | 'qwen'
export type IdentityChoice = 'continue_previous' | 'new_project' | 'not_me'

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
  customer_id?: string | null
  is_returning_customer?: boolean
  memory_summary?: string
  previous_visit_summaries?: string[]
  last_seen_at?: string | null
  customer_name: string | null
  phone: string | null
  room_type: string | null
  style: string | null
  budget: string | null
  has_pets?: boolean | null
  has_floor_heating?: boolean | null
  has_children?: boolean | null
  has_elderly?: boolean | null
  humid_environment?: boolean | null
  priorities?: Record<string, string>
  preferred_colors?: string[]
  rejected_colors?: string[]
  preferred_product_ids?: string[]
  rejected_product_ids?: string[]
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
  identity_frame_available?: boolean
  wave_debug: Record<string, unknown>
}

export type ChatResponse = {
  answer: string
  recommended_products: FlooringProduct[]
  customer_profile: CustomerProfile
  follow_up_suggestion: string
  state: SessionState
  provider_mode?: DialogueProvider
  provider_label?: string
  llm_degraded?: boolean
  needs_clarification?: boolean
  pending_slot?: string | null
  last_assistant_question?: string | null
  asr_confirmation_required?: boolean
  asr_suggested_text?: string | null
}

export type SessionStatusResponse = {
  state: SessionState
  status: Record<string, unknown>
  customer_profile: CustomerProfile
  provider_mode?: DialogueProvider
  provider_label?: string
}

export type IdentityRecognitionResult = {
  status: string
  candidate_found: boolean
  candidate_token?: string
  expires_in_seconds?: number
  requires_confirmation?: boolean
  confidence_band?: string
  valid_samples?: number
  message: string
  error?: string | null
}

export type IdentitySessionResponse = {
  ok: boolean
  session_id: string
  customer_profile: CustomerProfile
  returning_customer: boolean
  greeting: string
  provider_mode: DialogueProvider
  provider_label: string
  memory_loaded: boolean
}

export type IdentityEnrollResult = {
  ok: boolean
  status: string
  enrolled: boolean
  customer_id?: string
  template_count?: number
  valid_samples?: number
  stores_raw_photos?: boolean
  message: string
  error?: string | null
  customer_profile?: CustomerProfile
}

export type CompareRow = {
  field: string
  values: Record<string, unknown>
}

export type TTSStatus = {
  ok: boolean
  local_tts_available?: boolean
  local_tts_url?: string
  local_tts_health_url?: string
  openai_tts_configured: boolean
  openai_model?: string
  openai_voice?: string
  model?: string
  voice?: string
  fallback?: string
  auto_order?: string[]
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

export function getSessionStatus(sessionId = 'demo-session-001'): Promise<SessionStatusResponse> {
  return requestJson(`/api/session/status?session_id=${encodeURIComponent(sessionId)}`)
}

export function resetSession(sessionId = 'demo-session-001'): Promise<SessionStatusResponse> {
  return requestJson(`/api/session/reset?session_id=${encodeURIComponent(sessionId)}`, { method: 'POST' })
}

export function sendDemoEvent(event: string, sessionId = 'demo-session-001'): Promise<SessionStatusResponse> {
  return requestJson('/api/demo/event', {
    method: 'POST',
    body: JSON.stringify({ event, session_id: sessionId }),
  })
}

export function sendVoiceGreeting(text = '你好', sessionId = 'demo-session-001'): Promise<{
  accepted: boolean
  state: SessionState
  message: string
  status: Record<string, unknown>
}> {
  return requestJson('/api/greeting/voice', {
    method: 'POST',
    body: JSON.stringify({ text, session_id: sessionId }),
  })
}

export function sendChat(
  text: string,
  responseLanguage?: ResponseLanguage,
  sessionId = 'demo-session-001',
): Promise<ChatResponse> {
  return requestJson('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ text, response_language: responseLanguage, session_id: sessionId }),
  })
}

export function getIdentityStatus(): Promise<Record<string, unknown>> {
  return requestJson('/api/identity/status')
}

export function recognizeIdentity(providerMode?: DialogueProvider): Promise<IdentityRecognitionResult> {
  return requestJson('/api/identity/recognize', {
    method: 'POST',
    body: JSON.stringify({ provider_mode: providerMode ?? null }),
  })
}

export function startNewIdentitySession(providerMode?: DialogueProvider): Promise<IdentitySessionResponse> {
  return requestJson('/api/identity/session/new', {
    method: 'POST',
    body: JSON.stringify({ provider_mode: providerMode ?? null }),
  })
}

export function confirmIdentity(
  candidateToken: string,
  choice: IdentityChoice,
  providerMode?: DialogueProvider,
): Promise<IdentitySessionResponse> {
  return requestJson('/api/identity/confirm', {
    method: 'POST',
    body: JSON.stringify({
      candidate_token: candidateToken,
      choice,
      provider_mode: providerMode ?? null,
    }),
  })
}

export function enrollIdentity(
  sessionId: string,
  consent: boolean,
  displayName?: string,
): Promise<IdentityEnrollResult> {
  return requestJson('/api/identity/enroll', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      consent,
      display_name: displayName?.trim() || null,
    }),
  })
}

export function forgetIdentity(sessionId: string, deleteHistory = true): Promise<{
  ok: boolean
  deleted: boolean
  message: string
}> {
  return requestJson('/api/identity/me', {
    method: 'DELETE',
    body: JSON.stringify({ session_id: sessionId, delete_history: deleteHistory }),
  })
}

export function getTTSStatus(): Promise<TTSStatus> {
  return requestJson<TTSStatus>('/api/tts/status')
}

export async function synthesizeSpeech(
  text: string,
  language: ResponseLanguage,
  provider: TTSProvider = 'auto',
  voice?: string,
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/tts`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
    },
    body: JSON.stringify({ text, language, provider, voice }),
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
