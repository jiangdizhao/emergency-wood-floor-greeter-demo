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
  project_type?: string | null
  estimated_area_sqm?: number | null
  purchase_timeline?: string | null
  decision_stage?: string | null
  has_pets?: boolean | null
  has_floor_heating?: boolean | null
  has_children?: boolean | null
  has_elderly?: boolean | null
  humid_environment?: boolean | null
  priorities?: Record<string, string>
  primary_purchase_driver?: string | null
  preferred_colors?: string[]
  rejected_colors?: string[]
  preferred_product_ids?: string[]
  rejected_product_ids?: string[]
  special_needs: string[]
  concerns: string[]
  objections?: string[]
  recommended_product_ids: string[]
  conversation_summary: string
  follow_up_status: string
  follow_up_suggestion: string
  sales_stage?: string
  sales_objective?: string
  featured_collection_ids?: string[]
  lead_temperature?: string
  promotion_ids_presented?: string[]
  promotion_interest?: boolean | null
  contact_prompt_eligible?: boolean
  contact_opt_in?: boolean
  marketing_opt_in?: boolean
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
  sales_stage?: string
  sales_objective?: string
  featured_collections?: Array<Record<string, unknown>>
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

const ENGLISH_VOICE_BY_CHINESE_VOICE: Record<string, string> = {
  zm_yunxi: 'am_liam',
  zm_yunjian: 'am_michael',
  zm_yunxia: 'am_puck',
  zm_yunyang: 'am_onyx',
}

const EN_PRODUCT: Record<string, Partial<FlooringProduct>> = {
  'WF-SPC-001': {
    name: 'Light Grey Spruce SPC Click Flooring',
    type: 'SPC',
    color: 'light grey',
    style: ['modern minimalist', 'Scandinavian'],
    suitable_rooms: ['living room', 'bedroom', 'study', 'whole home'],
    price_range: 'mid-range',
    selling_points: ['strong water resistance', 'high wear resistance', 'suited to homes with pets and children', 'easy daily maintenance'],
  },
  'WF-WOOD-002': {
    name: 'Natural Oak Engineered Wood Flooring',
    type: 'engineered wood',
    color: 'natural oak',
    style: ['Japanese', 'Scandinavian', 'natural'],
    suitable_rooms: ['bedroom', 'living room'],
    price_range: 'upper-mid range',
    selling_points: ['natural underfoot feel', 'authentic wood grain', 'warm natural appearance', 'underfloor-heating compatibility'],
  },
  'WF-LAM-003': {
    name: 'Morning Mist Grey Laminate Flooring',
    type: 'laminate',
    color: 'grey tone',
    style: ['modern minimalist', 'contemporary luxury'],
    suitable_rooms: ['living room', 'study', 'rental property'],
    price_range: 'economy',
    selling_points: ['strong value for money', 'good wear resistance', 'suited to budget-conscious homes', 'straightforward installation and maintenance'],
  },
  'WF-SPC-004': {
    name: 'Dark Walnut Waterproof SPC Flooring',
    type: 'SPC',
    color: 'dark walnut',
    style: ['contemporary Chinese', 'contemporary luxury', 'modern'],
    suitable_rooms: ['living room', 'dining room', 'whole home'],
    price_range: 'upper-mid range',
    selling_points: ['rich dark-walnut appearance', 'strong water and wear resistance', 'suited to premium modern interiors', 'suited to high-traffic areas'],
  },
  'WF-WOOD-005': {
    name: 'Warm Light Oak Three-Layer Wood Flooring',
    type: 'three-layer wood',
    color: 'light oak',
    style: ['Scandinavian', 'natural timber', 'natural'],
    suitable_rooms: ['bedroom', 'study', 'living room'],
    price_range: 'premium',
    selling_points: ['comfortable underfoot feel', 'authentic natural wood texture', 'warm residential atmosphere', 'suited to premium homes'],
  },
  'WF-LAM-006': {
    name: 'Cream White High-Wear Laminate Flooring',
    type: 'laminate',
    color: 'cream white',
    style: ['cream-style interior', 'modern minimalist', 'Scandinavian'],
    suitable_rooms: ['bedroom', 'study', "children's room"],
    price_range: 'mid-range',
    selling_points: ['bright colour', 'wear-resistant and easy to maintain', "suited to bedrooms and children's rooms", 'soft overall appearance'],
  },
}

const EN_VALUE: Record<string, string> = {
  客厅: 'living room',
  卧室: 'bedroom',
  全屋: 'whole home',
  厨房: 'kitchen',
  书房: 'study',
  儿童房: "children's room",
  老人房: "older person's room",
  餐厅: 'dining room',
  出租房: 'rental property',
  现代简约: 'modern minimalist',
  北欧: 'Scandinavian',
  日式: 'Japanese',
  自然风: 'natural',
  轻奢: 'contemporary luxury',
  新中式: 'contemporary Chinese',
  现代: 'modern',
  原木: 'natural timber',
  奶油风: 'cream-style interior',
  经济: 'economy',
  中等: 'mid-range',
  偏高: 'upper-mid range',
  高端: 'premium',
  浅灰: 'light grey',
  浅灰色: 'light grey',
  灰调: 'grey tone',
  深胡桃色: 'dark walnut',
  原木色: 'natural oak',
  浅橡木色: 'light oak',
  奶油白: 'cream white',
  防水: 'water resistance',
  耐磨: 'wear resistance',
  环保: 'environmental documentation',
  价格: 'budget',
  脚感: 'underfoot feel',
  好清洁: 'easy cleaning',
  宠物: 'pets',
  地暖: 'underfloor heating',
  儿童: 'children',
  老人: 'older family members',
  潮湿环境: 'humid environment',
  新房装修: 'new-home fit-out',
  旧房翻新: 'existing-home renovation',
  局部改造: 'partial renovation',
  自住: 'owner-occupied home',
  立即: 'immediately',
  '1个月内': 'within one month',
  '1-3个月': 'within one to three months',
  '3个月以上': 'more than three months',
  待定: 'not decided yet',
  初步了解: 'early research',
  正在比较: 'comparing options',
  准备购买: 'preparing to purchase',
  等待家人决定: 'waiting for a family decision',
  价格顾虑: 'budget concern',
  环保顾虑: 'environmental-documentation concern',
  防水顾虑: 'water-resistance concern',
  维护顾虑: 'maintenance concern',
  脚感顾虑: 'underfoot-feel concern',
  需要商量: 'needs family discussion',
  需要比较: 'needs comparison',
  颜色顾虑: 'colour concern',
  未建档: 'not registered',
}

const IDENTITY_MESSAGES: Record<string, string> = {
  unavailable: 'Local face recognition is not available.',
  no_enrolled_customers: 'No customer face memory is currently registered on this PC.',
  no_face: 'A sufficiently clear face was not captured. Face the screen in good lighting and try again.',
  no_match: 'No trusted match was found. A new anonymous consultation will be started.',
  unstable_match: 'The face match was not stable enough. A new anonymous consultation will be started.',
  candidate_found: 'A previous local shopping record may have been found. Please confirm whether to continue.',
}

const EN_NEW_GREETING =
  'Hello, welcome to Senjing Flooring Living Gallery. I am Xiao Mu, your senior flooring consultant. I can help you rule out unsuitable materials, compare the practical value and trade-offs of different options, and form a main recommendation with a backup. Our demo focuses on durable easy-care family solutions, underfloor-heating options, natural wood comfort and practical value choices. Which point are you least willing to compromise on: budget, wear resistance, water resistance, underfoot feel, environmental documentation, or easy cleaning?'

export function getUILanguage(): ResponseLanguage {
  const configured = (window as Window & { __WOODFLOOR_LANGUAGE__?: string }).__WOODFLOOR_LANGUAGE__
  const stored = window.localStorage.getItem('woodfloor_ui_language')
  return configured === 'en' || stored === 'en' ? 'en' : 'zh'
}

function localizeValue(value: string | null | undefined): string | null {
  if (value == null) return null
  return EN_VALUE[value] ?? value
}

function localizeList(values: string[] | undefined): string[] {
  return (values ?? []).map((value) => EN_VALUE[value] ?? value)
}

function localizeProduct(product: FlooringProduct): FlooringProduct {
  if (getUILanguage() !== 'en') return product
  return { ...product, ...(EN_PRODUCT[product.id] ?? {}) }
}

function englishProfileSummary(profile: CustomerProfile): string {
  const parts: string[] = []
  if (profile.primary_purchase_driver) parts.push(`Primary requirement: ${localizeValue(profile.primary_purchase_driver)}`)
  if (profile.room_type) parts.push(`Room: ${localizeValue(profile.room_type)}`)
  if (profile.style) parts.push(`Style: ${localizeValue(profile.style)}`)
  if (profile.budget) parts.push(`Budget: ${localizeValue(profile.budget)}`)
  if (profile.estimated_area_sqm != null) parts.push(`Area: ${profile.estimated_area_sqm} m²`)
  if (profile.purchase_timeline) parts.push(`Timing: ${localizeValue(profile.purchase_timeline)}`)
  if (profile.has_pets) parts.push('Pets at home')
  if (profile.has_floor_heating) parts.push('Underfloor heating')
  if (profile.humid_environment) parts.push('Humid environment')
  return parts.length ? parts.join('; ') + '.' : 'The previous requirements are not yet complete.'
}

function localizeProfile(profile: CustomerProfile): CustomerProfile {
  if (getUILanguage() !== 'en') return profile
  const localized: CustomerProfile = {
    ...profile,
    room_type: localizeValue(profile.room_type),
    style: localizeValue(profile.style),
    budget: localizeValue(profile.budget),
    project_type: localizeValue(profile.project_type),
    purchase_timeline: localizeValue(profile.purchase_timeline),
    decision_stage: localizeValue(profile.decision_stage),
    primary_purchase_driver: localizeValue(profile.primary_purchase_driver),
    preferred_colors: localizeList(profile.preferred_colors),
    rejected_colors: localizeList(profile.rejected_colors),
    special_needs: localizeList(profile.special_needs),
    concerns: localizeList(profile.concerns),
    objections: localizeList(profile.objections),
    priorities: Object.fromEntries(
      Object.entries(profile.priorities ?? {}).map(([key, value]) => [EN_VALUE[key] ?? key, value]),
    ),
    follow_up_status: localizeValue(profile.follow_up_status) ?? profile.follow_up_status,
  }
  localized.conversation_summary = englishProfileSummary(profile)
  localized.memory_summary = profile.memory_summary ? englishProfileSummary(profile) : ''
  localized.previous_visit_summaries = (profile.previous_visit_summaries ?? []).map(() =>
    'A previous consultation summary is available after identity confirmation.',
  )
  localized.follow_up_suggestion = profile.follow_up_suggestion
    ? 'The store should follow up with the main and backup comparison, then confirm area, budget and installation timing.'
    : ''
  return localized
}

function englishGreeting(choice: IdentityChoice | 'new', response: IdentitySessionResponse): string {
  if (choice === 'new' || !response.returning_customer) return EN_NEW_GREETING
  if (choice === 'new_project') {
    return 'Welcome back. We are starting a new flooring project and will keep only the stable household background you confirmed. For this project, which point are you least willing to compromise on: budget, wear resistance, water resistance, underfoot feel, environmental documentation, or easy cleaning?'
  }
  return 'Welcome back. You have confirmed that you want to continue the previous flooring consultation. Would you like to continue with the previous main recommendation, or first tell me which requirement has changed?'
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json; charset=utf-8')
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
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

export async function getProducts(): Promise<{ products: FlooringProduct[] }> {
  const result = await requestJson<{ products: FlooringProduct[] }>('/api/products')
  return { products: result.products.map(localizeProduct) }
}

export async function getSessionStatus(sessionId = 'demo-session-001'): Promise<SessionStatusResponse> {
  const result = await requestJson<SessionStatusResponse>(`/api/session/status?session_id=${encodeURIComponent(sessionId)}`)
  return { ...result, customer_profile: localizeProfile(result.customer_profile) }
}

export async function resetSession(sessionId = 'demo-session-001'): Promise<SessionStatusResponse> {
  const result = await requestJson<SessionStatusResponse>(`/api/session/reset?session_id=${encodeURIComponent(sessionId)}`, { method: 'POST' })
  return { ...result, customer_profile: localizeProfile(result.customer_profile) }
}

export async function sendDemoEvent(event: string, sessionId = 'demo-session-001'): Promise<SessionStatusResponse> {
  const result = await requestJson<SessionStatusResponse>('/api/demo/event', {
    method: 'POST',
    body: JSON.stringify({ event, session_id: sessionId }),
  })
  return { ...result, customer_profile: localizeProfile(result.customer_profile) }
}

export function sendVoiceGreeting(
  text = getUILanguage() === 'en' ? 'hello' : '你好',
  sessionId = 'demo-session-001',
): Promise<{ accepted: boolean; state: SessionState; message: string; status: Record<string, unknown> }> {
  return requestJson('/api/greeting/voice', {
    method: 'POST',
    body: JSON.stringify({ text, session_id: sessionId }),
  })
}

export async function sendChat(
  text: string,
  _responseLanguage?: ResponseLanguage,
  sessionId = 'demo-session-001',
): Promise<ChatResponse> {
  const language = getUILanguage()
  const result = await requestJson<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ text, response_language: language, session_id: sessionId }),
  })
  return {
    ...result,
    recommended_products: result.recommended_products.map(localizeProduct),
    customer_profile: localizeProfile(result.customer_profile),
    follow_up_suggestion:
      language === 'en' && result.follow_up_suggestion
        ? 'The store should follow up with the main and backup comparison, then confirm area, budget and installation timing.'
        : result.follow_up_suggestion,
  }
}

export function getIdentityStatus(): Promise<Record<string, unknown>> {
  return requestJson('/api/identity/status')
}

export async function recognizeIdentity(providerMode?: DialogueProvider): Promise<IdentityRecognitionResult> {
  const result = await requestJson<IdentityRecognitionResult>('/api/identity/recognize', {
    method: 'POST',
    body: JSON.stringify({ provider_mode: providerMode ?? null, response_language: getUILanguage() }),
  })
  return getUILanguage() === 'en'
    ? { ...result, message: IDENTITY_MESSAGES[result.status] ?? 'The local identity check has completed.' }
    : result
}

export async function startNewIdentitySession(providerMode?: DialogueProvider): Promise<IdentitySessionResponse> {
  const result = await requestJson<IdentitySessionResponse>('/api/identity/session/new', {
    method: 'POST',
    body: JSON.stringify({ provider_mode: providerMode ?? null, response_language: getUILanguage() }),
  })
  return getUILanguage() === 'en'
    ? { ...result, greeting: englishGreeting('new', result), customer_profile: localizeProfile(result.customer_profile) }
    : result
}

export async function confirmIdentity(
  candidateToken: string,
  choice: IdentityChoice,
  providerMode?: DialogueProvider,
): Promise<IdentitySessionResponse> {
  const result = await requestJson<IdentitySessionResponse>('/api/identity/confirm', {
    method: 'POST',
    body: JSON.stringify({
      candidate_token: candidateToken,
      choice,
      provider_mode: providerMode ?? null,
      response_language: getUILanguage(),
    }),
  })
  return getUILanguage() === 'en'
    ? { ...result, greeting: englishGreeting(choice, result), customer_profile: localizeProfile(result.customer_profile) }
    : result
}

export async function enrollIdentity(
  sessionId: string,
  consent: boolean,
  displayName?: string,
): Promise<IdentityEnrollResult> {
  const result = await requestJson<IdentityEnrollResult>('/api/identity/enroll', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      consent,
      display_name: displayName?.trim() || null,
    }),
  })
  if (getUILanguage() !== 'en') return result
  return {
    ...result,
    message: result.enrolled
      ? 'Face features and the consultation memory have been saved locally. No raw face photo was stored.'
      : result.status === 'already_enrolled'
        ? 'This face may already be registered. Use returning-customer recognition instead of creating a duplicate record.'
        : 'Local face-memory enrolment was not completed. Face the screen in good lighting and try again.',
    customer_profile: result.customer_profile ? localizeProfile(result.customer_profile) : undefined,
  }
}

export async function forgetIdentity(sessionId: string, deleteHistory = true): Promise<{
  ok: boolean
  deleted: boolean
  message: string
}> {
  const result = await requestJson<{ ok: boolean; deleted: boolean; message: string }>('/api/identity/me', {
    method: 'DELETE',
    body: JSON.stringify({ session_id: sessionId, delete_history: deleteHistory }),
  })
  return getUILanguage() === 'en'
    ? {
        ...result,
        message: result.deleted
          ? 'Local face features, identity, contact consent and related history have been deleted.'
          : 'No deletable customer identity was bound to this session. Session contact records were still checked for removal.',
      }
    : result
}

export function getTTSStatus(): Promise<TTSStatus> {
  return requestJson<TTSStatus>('/api/tts/status')
}

export async function synthesizeSpeech(
  text: string,
  _language: ResponseLanguage,
  provider: TTSProvider = 'auto',
  voice?: string,
): Promise<Blob> {
  const language = getUILanguage()
  const selectedVoice = language === 'en' && voice ? ENGLISH_VOICE_BY_CHINESE_VOICE[voice] ?? voice : voice
  const response = await fetch(`${API_BASE_URL}/api/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ text, language, provider, voice: selectedVoice }),
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`${response.status} ${response.statusText}${detail ? `: ${detail}` : ''}`)
  }
  return await response.blob()
}

const EN_COMPARE_FIELD: Record<string, string> = {
  产品名称: 'Product',
  材质: 'Material',
  颜色: 'Colour',
  风格: 'Style',
  适合空间: 'Suitable rooms',
  防水: 'Water resistance',
  地暖适配: 'Underfloor heating',
  宠物友好: 'Pet friendly',
  '儿童/老人家庭': 'Children / older family members',
  耐磨等级: 'Wear rating',
  价格区间: 'Price range',
  规格: 'Dimensions',
  核心卖点: 'Key selling points',
}

function localizeCompareValue(productId: string, field: string, value: unknown): unknown {
  if (getUILanguage() !== 'en') return value
  const product = EN_PRODUCT[productId]
  if (field === '产品名称') return product?.name ?? value
  if (field === '材质') return product?.type ?? value
  if (field === '颜色') return product?.color ?? value
  if (field === '风格') return (product?.style ?? []).join(' / ') || value
  if (field === '适合空间') return (product?.suitable_rooms ?? []).join(' / ') || value
  if (field === '价格区间') return product?.price_range ?? value
  if (field === '核心卖点') return (product?.selling_points ?? []).slice(0, 3).join('; ') || value
  if (value === '是') return 'Yes'
  if (value === '否') return 'No'
  return value
}

export async function compareProducts(productIds: string[]): Promise<{ comparison: CompareRow[] }> {
  const result = await requestJson<{ comparison: CompareRow[] }>('/api/products/compare', {
    method: 'POST',
    body: JSON.stringify({ product_ids: productIds, response_language: getUILanguage() }),
  })
  if (getUILanguage() !== 'en') return result
  return {
    comparison: result.comparison.map((row) => ({
      field: EN_COMPARE_FIELD[row.field] ?? row.field,
      values: Object.fromEntries(
        Object.entries(row.values).map(([productId, value]) => [
          productId,
          localizeCompareValue(productId, row.field, value),
        ]),
      ),
    })),
  }
}
