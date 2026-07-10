import { useEffect, useMemo, useRef, useState } from 'react'
import {
  BarChart3,
  Check,
  ClipboardCheck,
  Mic,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  X,
} from 'lucide-react'
import './App.css'
import {
  compareProducts,
  getProducts,
  getSessionStatus,
  resetSession,
  sendChat,
  sendDemoEvent,
  startVision,
  synthesizeSpeech,
  type CompareRow,
  type CustomerProfile,
  type FlooringProduct,
} from './api'

type ChatMessage = {
  id: string
  role: 'agent' | 'customer'
  text: string
}

type VoiceStatus = 'idle' | 'listening' | 'processing' | 'speaking' | 'error'
type ScreenMode = 'welcome' | 'conversation' | 'summary'

type BrowserSpeechRecognitionAlternative = { transcript: string; confidence?: number }
type BrowserSpeechRecognitionResult = {
  isFinal?: boolean
  length: number
  [index: number]: BrowserSpeechRecognitionAlternative
}
type BrowserSpeechRecognitionEvent = {
  results: {
    length: number
    [index: number]: BrowserSpeechRecognitionResult
  }
}
type BrowserSpeechRecognitionErrorEvent = { error: string; message?: string }
type BrowserSpeechRecognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onstart: (() => void) | null
  onend: (() => void) | null
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null
}
type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition

const INTRODUCTION =
  '您好，欢迎来到木地板体验区。我是您的 AI 选购顾问小木。我可以根据房间、装修风格、预算，以及地暖、宠物和日常清洁需求，为您推荐合适的地板。请问您这次主要想为哪个空间选择地板呢？'

const QUICK_PROMPTS = [
  '客厅用，家里有宠物，希望耐磨又好清洁。',
  '卧室用，喜欢北欧原木风，想要脚感舒服。',
  '家里有地暖，应该选哪种地板？',
  '南方比较潮湿，想重点看看防水性能。',
]

const INITIAL_PROFILE: CustomerProfile = {
  session_id: 'demo-session-001',
  customer_name: null,
  phone: null,
  room_type: null,
  style: null,
  budget: null,
  special_needs: [],
  concerns: [],
  recommended_product_ids: [],
  conversation_summary: '',
  follow_up_status: '未建档',
  follow_up_suggestion: '',
}

function getRecognitionConstructor(): BrowserSpeechRecognitionConstructor | null {
  const speechWindow = window as Window & {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor
  }
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null
}

function extractTranscript(event: BrowserSpeechRecognitionEvent): string {
  let transcript = ''
  for (let i = 0; i < event.results.length; i += 1) {
    const result = event.results[i]
    if (result.length > 0) transcript += result[0].transcript
  }
  return transcript.trim()
}

function createMessage(role: ChatMessage['role'], text: string): ChatMessage {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    text,
  }
}

function yesNo(value: boolean): string {
  return value ? '支持' : '需确认'
}

function buildSummary(profile: CustomerProfile, recommendedProducts: FlooringProduct[]): string {
  const parts = [
    `铺装空间：${profile.room_type ?? '尚未确认'}`,
    `偏好风格：${profile.style ?? '尚未确认'}`,
    `预算区间：${profile.budget ?? '尚未确认'}`,
    `特殊需求：${profile.special_needs.length ? profile.special_needs.join('、') : '暂无明确要求'}`,
    `重点关注：${profile.concerns.length ? profile.concerns.join('、') : '尚未确认'}`,
    `推荐产品：${recommendedProducts.length ? recommendedProducts.map((product) => product.name).join('、') : '需要继续了解需求后推荐'}`,
  ]
  return parts.join('；') + '。'
}

function App() {
  const [screenMode, setScreenMode] = useState<ScreenMode>('welcome')
  const [products, setProducts] = useState<FlooringProduct[]>([])
  const [recommendedProducts, setRecommendedProducts] = useState<FlooringProduct[]>([])
  const [profile, setProfile] = useState<CustomerProfile>(INITIAL_PROFILE)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputText, setInputText] = useState('')
  const [compareOpen, setCompareOpen] = useState(false)
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [compareRows, setCompareRows] = useState<CompareRow[]>([])
  const [summaryText, setSummaryText] = useState('')
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>('idle')
  const [lastTranscript, setLastTranscript] = useState('')

  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  const speechRecognitionSupported = useMemo(() => getRecognitionConstructor() !== null, [])
  const speechSynthesisSupported = useMemo(
    () => 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window,
    [],
  )
  const recommendedIds = useMemo(
    () => new Set(recommendedProducts.map((product) => product.id)),
    [recommendedProducts],
  )

  useEffect(() => {
    void loadInitialData()
    // The camera remains available to the backend for future customer recognition,
    // but no camera image or engineering telemetry is exposed in the customer UI.
    void startVision().catch((visionError: unknown) => {
      console.warn('Background vision service is unavailable:', visionError)
    })
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, voiceStatus])

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
      audioRef.current?.pause()
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
      if (speechSynthesisSupported) window.speechSynthesis.cancel()
    }
  }, [speechSynthesisSupported])

  async function loadInitialData() {
    try {
      const [catalog, session] = await Promise.all([getProducts(), getSessionStatus()])
      setProducts(catalog.products)
      setProfile(session.customer_profile)
      const savedIds = new Set(session.customer_profile.recommended_product_ids)
      setRecommendedProducts(catalog.products.filter((product) => savedIds.has(product.id)))
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : String(loadError))
    }
  }

  async function runAction(label: string, action: () => Promise<void>) {
    setBusyAction(label)
    setError(null)
    try {
      await action()
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError))
    } finally {
      setBusyAction(null)
    }
  }

  function appendMessage(role: ChatMessage['role'], text: string) {
    setMessages((current) => [...current, createMessage(role, text)])
  }

  function stopSpeaking() {
    audioRef.current?.pause()
    audioRef.current = null
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current)
      audioUrlRef.current = null
    }
    if (speechSynthesisSupported) window.speechSynthesis.cancel()
    setVoiceStatus('idle')
  }

  async function speakWithBrowser(text: string): Promise<void> {
    if (!speechSynthesisSupported) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = 1
    utterance.pitch = 1
    await new Promise<void>((resolve) => {
      utterance.onstart = () => setVoiceStatus('speaking')
      utterance.onend = () => {
        setVoiceStatus('idle')
        resolve()
      }
      utterance.onerror = () => {
        setVoiceStatus('error')
        resolve()
      }
      window.speechSynthesis.speak(utterance)
    })
  }

  async function speakText(text: string): Promise<void> {
    if (!text.trim()) return
    stopSpeaking()
    setVoiceStatus('speaking')
    try {
      const audioBlob = await synthesizeSpeech(text, 'zh', 'auto')
      const audioUrl = URL.createObjectURL(audioBlob)
      audioUrlRef.current = audioUrl
      const audio = new Audio(audioUrl)
      audioRef.current = audio
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve()
        audio.onerror = () => reject(new Error('语音播放失败'))
        audio.play().catch(reject)
      })
      URL.revokeObjectURL(audioUrl)
      audioUrlRef.current = null
      audioRef.current = null
      setVoiceStatus('idle')
    } catch (ttsError) {
      console.warn('Backend TTS unavailable, using browser speech synthesis:', ttsError)
      await speakWithBrowser(text)
    }
  }

  async function handleStartConsultation() {
    await runAction('start', async () => {
      recognitionRef.current?.abort()
      stopSpeaking()
      const session = await resetSession()
      setProfile(session.customer_profile)
      setRecommendedProducts([])
      setCompareIds([])
      setCompareRows([])
      setInputText('')
      setLastTranscript('')
      setSummaryText('')
      setMessages([createMessage('agent', INTRODUCTION)])
      setScreenMode('conversation')
      await sendDemoEvent('intro_started').catch(() => undefined)
      await sendDemoEvent('intro_finished').catch(() => undefined)
      await speakText(INTRODUCTION)
    })
  }

  async function handleUserMessage(rawText: string) {
    const text = rawText.trim()
    if (!text) return
    appendMessage('customer', text)
    setInputText('')
    setVoiceStatus('processing')
    try {
      const response = await sendChat(text, 'zh')
      appendMessage('agent', response.answer)
      setRecommendedProducts(response.recommended_products)
      setProfile(response.customer_profile)
      await speakText(response.answer)
    } catch (chatError) {
      setVoiceStatus('error')
      throw chatError
    }
  }

  async function handleTextSubmit() {
    const text = inputText.trim()
    if (!text || busyAction !== null) return
    await runAction('chat', async () => handleUserMessage(text))
  }

  async function startListening() {
    const Recognition = getRecognitionConstructor()
    if (!Recognition) {
      setError('当前浏览器不支持语音识别，请使用 Chrome 或 Edge，也可以直接输入文字。')
      return
    }

    stopSpeaking()
    recognitionRef.current?.abort()
    const recognition = new Recognition()
    recognitionRef.current = recognition
    recognition.lang = 'zh-CN'
    recognition.continuous = false
    recognition.interimResults = false
    recognition.maxAlternatives = 1
    recognition.onstart = () => {
      setVoiceStatus('listening')
      setError(null)
    }
    recognition.onerror = (event) => {
      console.warn('Speech recognition error:', event.error, event.message)
      setError('没有听清，请再说一次，或者使用文字输入。')
      setVoiceStatus('error')
      recognitionRef.current = null
    }
    recognition.onend = () => {
      recognitionRef.current = null
      setVoiceStatus((current) => (current === 'listening' ? 'idle' : current))
    }
    recognition.onresult = (event) => {
      const transcript = extractTranscript(event)
      setLastTranscript(transcript)
      if (!transcript) {
        setVoiceStatus('idle')
        return
      }
      setVoiceStatus('processing')
      void runAction('chat', async () => handleUserMessage(transcript))
    }

    try {
      recognition.start()
    } catch (recognitionError) {
      setVoiceStatus('error')
      setError(recognitionError instanceof Error ? recognitionError.message : String(recognitionError))
    }
  }

  function stopListening() {
    recognitionRef.current?.stop()
    recognitionRef.current = null
    setVoiceStatus('idle')
  }

  async function handleCompareToggle(productId: string) {
    const nextIds = compareIds.includes(productId)
      ? compareIds.filter((id) => id !== productId)
      : [...compareIds, productId].slice(-2)
    setCompareIds(nextIds)
    if (nextIds.length === 2) {
      await runAction('compare', async () => {
        const result = await compareProducts(nextIds)
        setCompareRows(result.comparison)
      })
    } else {
      setCompareRows([])
    }
  }

  async function handleFinishAndSummarize() {
    await runAction('summary', async () => {
      stopListening()
      const summary = buildSummary(profile, recommendedProducts)
      setSummaryText(summary)
      setScreenMode('summary')
      await sendDemoEvent('end').catch(() => undefined)
      await speakText(`好的，我为您总结一下本次咨询。${summary}`)
    })
  }

  async function handleRestart() {
    await runAction('restart', async () => {
      recognitionRef.current?.abort()
      stopSpeaking()
      const session = await resetSession()
      setProfile(session.customer_profile)
      setRecommendedProducts([])
      setMessages([])
      setInputText('')
      setCompareIds([])
      setCompareRows([])
      setSummaryText('')
      setLastTranscript('')
      setCompareOpen(false)
      setScreenMode('welcome')
    })
  }

  const avatarStatus = voiceStatus === 'error' ? 'idle' : voiceStatus

  return (
    <main className="app-shell">
      {error && (
        <div className="friendly-alert" role="status">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="关闭提示">
            <X size={18} />
          </button>
        </div>
      )}

      {screenMode === 'welcome' && (
        <section className="welcome-screen">
          <div className="brand-mark">
            <Sparkles size={20} />
            <span>木地板 AI 选购顾问</span>
          </div>
          <ConsultantAvatar status="idle" large />
          <div className="welcome-copy">
            <p className="welcome-kicker">您好，我是小木</p>
            <h1>帮您更轻松地选到合适的木地板</h1>
            <p>告诉我您的房间、风格、预算和生活需求，我会为您推荐、比较并整理选购要点。</p>
          </div>
          <button
            type="button"
            className="primary-cta"
            onClick={() => void handleStartConsultation()}
            disabled={busyAction !== null}
          >
            <Sparkles size={22} />
            {busyAction === 'start' ? '正在为您准备…' : '开始咨询'}
          </button>
          <p className="privacy-note">点击后开始本次咨询。摄像头画面不会显示在屏幕上。</p>
        </section>
      )}

      {screenMode === 'conversation' && (
        <section className="consultation-screen">
          <header className="customer-header">
            <div className="brand-title">
              <span className="mini-logo"><Sparkles size={17} /></span>
              <div>
                <strong>小木 AI 导购</strong>
                <span>{voiceStatusLabel(voiceStatus)}</span>
              </div>
            </div>
            <button type="button" className="quiet-button" onClick={() => void handleRestart()} disabled={busyAction !== null}>
              <RotateCcw size={17} />
              重新开始
            </button>
          </header>

          <div className="consultation-layout">
            <aside className="assistant-stage">
              <ConsultantAvatar status={avatarStatus} />
              <div className="assistant-status">
                <span className={`status-pulse ${avatarStatus}`} />
                <strong>{voiceStatusLabel(voiceStatus)}</strong>
                <p>{lastTranscript ? `刚刚听到：“${lastTranscript}”` : '您可以直接说出需求，也可以输入文字。'}</p>
              </div>
              <div className="quick-start-list">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setInputText(prompt)}
                    disabled={busyAction !== null}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </aside>

            <section className="conversation-card">
              <div className="chat-log" aria-live="polite">
                {messages.map((message) => (
                  <div key={message.id} className={`message-row ${message.role}`}>
                    <div className="message-bubble">
                      <span>{message.role === 'agent' ? '小木' : '我'}</span>
                      <p>{message.text}</p>
                    </div>
                  </div>
                ))}
                {voiceStatus === 'processing' && (
                  <div className="message-row agent">
                    <div className="message-bubble thinking-bubble">
                      <span>小木</span>
                      <p>正在为您整理合适的建议<span className="typing-dots">•••</span></p>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {recommendedProducts.length > 0 && (
                <div className="recommendation-strip">
                  <div>
                    <Sparkles size={18} />
                    <span>为您推荐</span>
                  </div>
                  {recommendedProducts.map((product) => (
                    <button key={product.id} type="button" onClick={() => setCompareOpen(true)}>
                      {product.name}
                    </button>
                  ))}
                </div>
              )}

              <div className="composer">
                <textarea
                  value={inputText}
                  onChange={(event) => setInputText(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      void handleTextSubmit()
                    }
                  }}
                  placeholder="例如：客厅用，家里有宠物，希望耐磨好清洁…"
                  rows={2}
                />
                <button
                  type="button"
                  className="send-button"
                  onClick={() => void handleTextSubmit()}
                  disabled={!inputText.trim() || busyAction !== null}
                  aria-label="发送"
                >
                  <Send size={21} />
                </button>
              </div>

              <div className="primary-actions">
                <button
                  type="button"
                  className={`voice-button ${voiceStatus === 'listening' ? 'active' : ''}`}
                  onClick={() => (voiceStatus === 'listening' ? stopListening() : void startListening())}
                  disabled={!speechRecognitionSupported || (busyAction !== null && voiceStatus !== 'listening')}
                >
                  {voiceStatus === 'listening' ? <Square size={20} /> : <Mic size={22} />}
                  {voiceStatus === 'listening' ? '结束收音' : '点击说话'}
                </button>
                <button type="button" onClick={() => setCompareOpen(true)} disabled={products.length === 0}>
                  <BarChart3 size={21} />
                  产品对比
                </button>
                <button type="button" onClick={() => void handleFinishAndSummarize()} disabled={busyAction !== null}>
                  <ClipboardCheck size={21} />
                  结束并总结
                </button>
              </div>
            </section>
          </div>
        </section>
      )}

      {screenMode === 'summary' && (
        <section className="summary-screen">
          <div className="summary-heading">
            <div className="summary-icon"><ClipboardCheck size={30} /></div>
            <p>本次咨询已完成</p>
            <h1>您的选购要点</h1>
          </div>
          <div className="summary-grid">
            <SummaryItem label="铺装空间" value={profile.room_type ?? '尚未确认'} />
            <SummaryItem label="偏好风格" value={profile.style ?? '尚未确认'} />
            <SummaryItem label="预算区间" value={profile.budget ?? '尚未确认'} />
            <SummaryItem label="特殊需求" value={profile.special_needs.length ? profile.special_needs.join('、') : '暂无明确要求'} />
            <SummaryItem label="重点关注" value={profile.concerns.length ? profile.concerns.join('、') : '尚未确认'} />
            <SummaryItem
              label="推荐产品"
              value={recommendedProducts.length ? recommendedProducts.map((product) => product.name).join('、') : '需要继续了解需求'}
            />
          </div>
          <div className="summary-narrative">
            <Sparkles size={20} />
            <p>{summaryText}</p>
          </div>
          {profile.follow_up_suggestion && (
            <div className="follow-up-card">
              <Check size={20} />
              <div>
                <strong>下一步建议</strong>
                <p>{profile.follow_up_suggestion}</p>
              </div>
            </div>
          )}
          <div className="summary-actions">
            <button type="button" onClick={() => setScreenMode('conversation')}>
              继续咨询
            </button>
            <button type="button" className="primary-cta compact" onClick={() => void handleRestart()} disabled={busyAction !== null}>
              <RotateCcw size={20} />
              开始新的咨询
            </button>
          </div>
        </section>
      )}

      {compareOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setCompareOpen(false)}>
          <section className="compare-modal" role="dialog" aria-modal="true" aria-label="产品对比" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <p>最多选择两款</p>
                <h2>产品对比</h2>
              </div>
              <button type="button" className="icon-button" onClick={() => setCompareOpen(false)} aria-label="关闭产品对比">
                <X size={23} />
              </button>
            </header>

            <div className="compare-product-grid">
              {products.map((product) => (
                <ProductChoiceCard
                  key={product.id}
                  product={product}
                  recommended={recommendedIds.has(product.id)}
                  selected={compareIds.includes(product.id)}
                  onToggle={() => void handleCompareToggle(product.id)}
                />
              ))}
            </div>

            {compareIds.length < 2 && <p className="compare-hint">请选择两款产品，即可查看完整参数对比。</p>}

            {compareRows.length > 0 && (
              <div className="compare-table-wrap">
                <table>
                  <tbody>
                    {compareRows.map((row) => (
                      <tr key={row.field}>
                        <th>{row.field}</th>
                        {compareIds.map((id) => (
                          <td key={id}>{String(row.values[id] ?? '—')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  )
}

function voiceStatusLabel(status: VoiceStatus): string {
  const labels: Record<VoiceStatus, string> = {
    idle: '随时为您服务',
    listening: '正在认真听您说',
    processing: '正在整理建议',
    speaking: '正在为您讲解',
    error: '请再试一次',
  }
  return labels[status]
}

function ConsultantAvatar({ status, large = false }: { status: VoiceStatus; large?: boolean }) {
  return (
    <div className={`consultant-avatar ${status} ${large ? 'large' : ''}`} aria-label="AI 导购小木">
      <div className="avatar-halo" />
      <svg viewBox="0 0 260 300" role="img" aria-hidden="true">
        <defs>
          <linearGradient id="shirt-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#b87545" />
            <stop offset="100%" stopColor="#7d4529" />
          </linearGradient>
          <linearGradient id="hair-gradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#442a23" />
            <stop offset="100%" stopColor="#251814" />
          </linearGradient>
        </defs>
        <ellipse cx="130" cy="279" rx="91" ry="17" fill="rgba(56,35,25,.12)" />
        <path d="M51 282c8-56 38-85 79-85s72 29 80 85" fill="url(#shirt-gradient)" />
        <path d="M104 199h52v39c-8 13-44 13-52 0z" fill="#e9b999" />
        <path d="M78 111c0-55 24-85 56-85 42 0 61 34 56 88l-10 59c-8 36-28 54-50 54s-43-18-51-54z" fill="#f2c7a8" />
        <path d="M74 120C61 61 88 18 137 18c44 0 68 35 57 99-12-6-21-22-24-38-20 22-49 30-87 27-1 8-4 12-9 14z" fill="url(#hair-gradient)" />
        <path d="M78 113c-14 2-17 17-10 32 4 9 10 14 17 13" fill="#efc2a2" />
        <path d="M185 113c14 2 17 17 10 32-4 9-10 14-17 13" fill="#efc2a2" />
        <path d="M103 130c7-5 15-5 22 0" stroke="#5b3c31" strokeWidth="4" strokeLinecap="round" fill="none" />
        <path d="M142 130c7-5 15-5 22 0" stroke="#5b3c31" strokeWidth="4" strokeLinecap="round" fill="none" />
        <ellipse cx="114" cy="137" rx="4" ry="5" fill="#34231f" />
        <ellipse cx="153" cy="137" rx="4" ry="5" fill="#34231f" />
        <path d="M132 142c-3 10-4 17 3 20" stroke="#d69c7d" strokeWidth="3" strokeLinecap="round" fill="none" />
        <path className="avatar-mouth" d="M115 177c11 9 25 9 37 0" stroke="#9a4b4c" strokeWidth="4" strokeLinecap="round" fill="none" />
        <path d="M99 207l31 25 31-25 15 17-18 58H102l-18-58z" fill="#f8f4ef" />
        <path d="M130 232v50" stroke="#d6c6b7" strokeWidth="3" />
        <circle cx="130" cy="252" r="4" fill="#9a6544" />
      </svg>
      <div className="voice-rings"><span /><span /><span /></div>
    </div>
  )
}

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ProductChoiceCard({
  product,
  recommended,
  selected,
  onToggle,
}: {
  product: FlooringProduct
  recommended: boolean
  selected: boolean
  onToggle: () => void
}) {
  return (
    <article className={`choice-card ${selected ? 'selected' : ''}`}>
      <div className="floor-swatch" data-tone={product.color}>
        <span>{product.color}</span>
      </div>
      <div className="choice-card-body">
        <div className="choice-card-heading">
          <div>
            <span className="sku">{product.id}</span>
            <h3>{product.name}</h3>
          </div>
          {recommended && <span className="recommend-badge">推荐</span>}
        </div>
        <p>{product.type} · {product.price_range} · {product.wear_level}</p>
        <div className="feature-chips">
          <span>防水 {yesNo(product.waterproof)}</span>
          <span>地暖 {yesNo(product.floor_heating)}</span>
          <span>宠物 {yesNo(product.pet_friendly)}</span>
        </div>
        <button type="button" className={selected ? 'selected' : ''} onClick={onToggle}>
          {selected ? <Check size={17} /> : <BarChart3 size={17} />}
          {selected ? '已加入对比' : '加入对比'}
        </button>
      </div>
    </article>
  )
}

export default App
