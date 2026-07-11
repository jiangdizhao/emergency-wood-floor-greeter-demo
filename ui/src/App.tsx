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
import './AgentSelector.css'
import './IdentityMemory.css'
import {
  compareProducts,
  confirmIdentity,
  enrollIdentity,
  getProducts,
  recognizeIdentity,
  sendChat,
  sendDemoEvent,
  startNewIdentitySession,
  startVision,
  synthesizeSpeech,
  type CompareRow,
  type CustomerProfile,
  type FlooringProduct,
  type IdentityChoice,
  type IdentitySessionResponse,
} from './api'

type ChatMessage = {
  id: string
  role: 'agent' | 'customer'
  text: string
}

type VoiceStatus = 'idle' | 'listening' | 'processing' | 'speaking' | 'error'
type ScreenMode = 'welcome' | 'conversation' | 'summary'
type ConsultantId = 'yunxi' | 'yunjian' | 'yunxia' | 'yunyang'
type ConsultantAccessory = 'none' | 'glasses' | 'young' | 'mature'

type ConsultantProfile = {
  id: ConsultantId
  displayName: string
  styleName: string
  description: string
  voice: string
  previewText: string
  shirtStart: string
  shirtEnd: string
  hairStart: string
  hairEnd: string
  skin: string
  accessory: ConsultantAccessory
}

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

const CONSULTANTS: ConsultantProfile[] = [
  {
    id: 'yunxi',
    displayName: '云希',
    styleName: '温暖亲和',
    description: '语气柔和，适合耐心了解家庭需求。',
    voice: 'zm_yunxi',
    previewText: '您好，我是温暖亲和风格的导购小木，很高兴为您服务。',
    shirtStart: '#b87545',
    shirtEnd: '#7d4529',
    hairStart: '#442a23',
    hairEnd: '#251814',
    skin: '#f2c7a8',
    accessory: 'none',
  },
  {
    id: 'yunjian',
    displayName: '云健',
    styleName: '沉稳专业',
    description: '表达稳重，适合讲解材质与性能差异。',
    voice: 'zm_yunjian',
    previewText: '您好，我是沉稳专业风格的导购小木，我会为您清晰比较产品特点。',
    shirtStart: '#536678',
    shirtEnd: '#283845',
    hairStart: '#31363d',
    hairEnd: '#15191d',
    skin: '#efc3a4',
    accessory: 'glasses',
  },
  {
    id: 'yunxia',
    displayName: '云夏',
    styleName: '年轻活力',
    description: '节奏轻快，适合现代家居和年轻家庭。',
    voice: 'zm_yunxia',
    previewText: '您好，我是年轻活力风格的导购小木，我们一起找到更适合您家的方案。',
    shirtStart: '#5f8a73',
    shirtEnd: '#315b49',
    hairStart: '#3f2d24',
    hairEnd: '#201711',
    skin: '#f0bd98',
    accessory: 'young',
  },
  {
    id: 'yunyang',
    displayName: '云扬',
    styleName: '成熟自信',
    description: '讲解清晰，适合快速形成购买判断。',
    voice: 'zm_yunyang',
    previewText: '您好，我是成熟自信风格的导购小木，我会帮您抓住选购重点。',
    shirtStart: '#76645c',
    shirtEnd: '#40332d',
    hairStart: '#56504c',
    hairEnd: '#26221f',
    skin: '#eab995',
    accessory: 'mature',
  },
]

const QUICK_PROMPTS = [
  '客厅用，家里有宠物，希望耐磨又好清洁。',
  '卧室用，喜欢北欧原木风，想要脚感舒服。',
  '家里有地暖，应该选哪种地板？',
  '南方比较潮湿，想重点看看防水性能。',
]

const INITIAL_PROFILE: CustomerProfile = {
  session_id: 'demo-session-001',
  customer_id: null,
  is_returning_customer: false,
  memory_summary: '',
  previous_visit_summaries: [],
  last_seen_at: null,
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

function joinTranscript(...parts: string[]): string {
  return parts
    .map((part) => part.trim())
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
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
  const [selectedConsultantId, setSelectedConsultantId] = useState<ConsultantId>('yunxi')
  const [sessionId, setSessionId] = useState('demo-session-001')
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

  const [identityCandidateToken, setIdentityCandidateToken] = useState<string | null>(null)
  const [identityPromptOpen, setIdentityPromptOpen] = useState(false)
  const [identityMessage, setIdentityMessage] = useState('')
  const [enrollmentOpen, setEnrollmentOpen] = useState(false)
  const [enrollmentName, setEnrollmentName] = useState('')
  const [enrollmentConsent, setEnrollmentConsent] = useState(false)

  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const listeningSessionRef = useRef(false)
  const manualStopRef = useRef(false)
  const capturedTranscriptRef = useRef('')
  const restartTimerRef = useRef<number | null>(null)
  const finalizeInFlightRef = useRef(false)

  const selectedConsultant = useMemo(
    () => CONSULTANTS.find((consultant) => consultant.id === selectedConsultantId) ?? CONSULTANTS[0],
    [selectedConsultantId],
  )
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
    void startVision().catch((visionError: unknown) => {
      console.warn('Background vision service is unavailable:', visionError)
    })
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, voiceStatus])

  useEffect(() => {
    return () => {
      listeningSessionRef.current = false
      manualStopRef.current = false
      if (restartTimerRef.current !== null) window.clearTimeout(restartTimerRef.current)
      recognitionRef.current?.abort()
      audioRef.current?.pause()
      if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
      if (speechSynthesisSupported) window.speechSynthesis.cancel()
    }
  }, [speechSynthesisSupported])

  async function loadInitialData() {
    try {
      const catalog = await getProducts()
      setProducts(catalog.products)
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

  async function speakText(text: string, consultant: ConsultantProfile = selectedConsultant): Promise<void> {
    if (!text.trim()) return
    stopSpeaking()
    setVoiceStatus('speaking')
    try {
      const audioBlob = await synthesizeSpeech(text, 'zh', 'local', consultant.voice)
      await playAudioBlob(audioBlob)
    } catch (localTtsError) {
      console.warn('Selected local Kokoro voice unavailable, trying normal fallback chain:', localTtsError)
      try {
        const fallbackBlob = await synthesizeSpeech(text, 'zh', 'auto')
        await playAudioBlob(fallbackBlob)
      } catch (fallbackError) {
        console.warn('Backend TTS unavailable, using browser speech synthesis:', fallbackError)
        await speakWithBrowser(text)
      }
    }
  }

  async function playAudioBlob(audioBlob: Blob): Promise<void> {
    const audioUrl = URL.createObjectURL(audioBlob)
    audioUrlRef.current = audioUrl
    const audio = new Audio(audioUrl)
    audioRef.current = audio
    try {
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve()
        audio.onerror = () => reject(new Error('语音播放失败'))
        audio.play().catch(reject)
      })
    } finally {
      URL.revokeObjectURL(audioUrl)
      if (audioUrlRef.current === audioUrl) audioUrlRef.current = null
      if (audioRef.current === audio) audioRef.current = null
    }
    setVoiceStatus('idle')
  }

  async function handleConsultantSelection(consultant: ConsultantProfile, playPreview = true) {
    if (voiceStatus === 'listening' || busyAction !== null) return
    setSelectedConsultantId(consultant.id)
    if (playPreview) await speakText(consultant.previewText, consultant)
  }

  async function activateSession(session: IdentitySessionResponse) {
    setSessionId(session.session_id)
    setProfile(session.customer_profile)
    const savedIds = new Set(session.customer_profile.recommended_product_ids)
    setRecommendedProducts(products.filter((product) => savedIds.has(product.id)))
    setCompareIds([])
    setCompareRows([])
    setInputText('')
    setLastTranscript('')
    setSummaryText('')
    setMessages([createMessage('agent', session.greeting)])
    setScreenMode('conversation')
    setIdentityMessage(session.returning_customer ? '已加载经您确认的本地历史选购记忆。' : '')
    await sendDemoEvent('intro_started', session.session_id).catch(() => undefined)
    await sendDemoEvent('intro_finished', session.session_id).catch(() => undefined)
    await speakText(session.greeting)
  }

  async function handleStartConsultation() {
    await runAction('start', async () => {
      cancelListening()
      stopSpeaking()
      setIdentityMessage('正在本机检查是否存在您之前同意保存的选购记录…')

      let recognition: Awaited<ReturnType<typeof recognizeIdentity>> | null = null
      try {
        recognition = await recognizeIdentity()
      } catch (recognitionError) {
        console.warn('Face identity check unavailable; starting anonymous session:', recognitionError)
      }

      if (recognition?.candidate_found && recognition.candidate_token) {
        setIdentityCandidateToken(recognition.candidate_token)
        setIdentityMessage(recognition.message)
        setIdentityPromptOpen(true)
        return
      }

      const session = await startNewIdentitySession()
      await activateSession(session)
    })
  }

  async function handleIdentityChoice(choice: IdentityChoice) {
    const token = identityCandidateToken
    if (!token) return
    await runAction('identity', async () => {
      const session = await confirmIdentity(token, choice)
      setIdentityPromptOpen(false)
      setIdentityCandidateToken(null)
      await activateSession(session)
    })
  }

  async function handleEnrollment() {
    if (!enrollmentConsent) {
      setError('请先确认您同意仅在本机保存人脸特征和本次选购记录。')
      return
    }
    await runAction('enroll', async () => {
      const result = await enrollIdentity(sessionId, true, enrollmentName)
      if (!result.enrolled) throw new Error(result.message)
      if (result.customer_profile) setProfile(result.customer_profile)
      setIdentityMessage(result.message)
      setEnrollmentOpen(false)
      setEnrollmentConsent(false)
      setEnrollmentName('')
    })
  }

  async function handleUserMessage(rawText: string) {
    const text = rawText.trim()
    if (!text) return
    appendMessage('customer', text)
    setInputText('')
    setVoiceStatus('processing')
    try {
      const response = await sendChat(text, 'zh', sessionId)
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
    if (listeningSessionRef.current) return

    stopSpeaking()
    cancelListening()
    listeningSessionRef.current = true
    manualStopRef.current = false
    capturedTranscriptRef.current = ''
    setLastTranscript('')
    setError(null)
    setVoiceStatus('listening')
    startRecognitionCycle(Recognition)
  }

  function startRecognitionCycle(Recognition: BrowserSpeechRecognitionConstructor) {
    if (!listeningSessionRef.current) return

    const recognition = new Recognition()
    let cycleFinalText = ''
    let cycleInterimText = ''
    recognitionRef.current = recognition
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    recognition.onstart = () => {
      if (listeningSessionRef.current) {
        setVoiceStatus('listening')
        setError(null)
      }
    }

    recognition.onresult = (event) => {
      const finalParts: string[] = []
      const interimParts: string[] = []
      for (let i = 0; i < event.results.length; i += 1) {
        const result = event.results[i]
        const text = result.length > 0 ? result[0].transcript.trim() : ''
        if (!text) continue
        if (result.isFinal) finalParts.push(text)
        else interimParts.push(text)
      }
      cycleFinalText = joinTranscript(...finalParts)
      cycleInterimText = joinTranscript(...interimParts)
      setLastTranscript(joinTranscript(capturedTranscriptRef.current, cycleFinalText, cycleInterimText))
    }

    recognition.onerror = (event) => {
      console.warn('Speech recognition error:', event.error, event.message)
      if (event.error === 'aborted' || event.error === 'no-speech') return

      if (['not-allowed', 'service-not-allowed', 'audio-capture', 'network'].includes(event.error)) {
        listeningSessionRef.current = false
        manualStopRef.current = false
        setVoiceStatus('error')
        setError(
          event.error === 'network'
            ? '语音识别服务暂时不可用，请使用文字输入。'
            : '无法使用麦克风，请检查浏览器麦克风权限。',
        )
      }
    }

    recognition.onend = () => {
      if (recognitionRef.current === recognition) recognitionRef.current = null
      const cycleText = joinTranscript(cycleFinalText, cycleInterimText)
      if (cycleText) {
        capturedTranscriptRef.current = joinTranscript(capturedTranscriptRef.current, cycleText)
        setLastTranscript(capturedTranscriptRef.current)
      }

      if (manualStopRef.current) {
        manualStopRef.current = false
        void finalizeCapturedSpeech()
        return
      }

      if (listeningSessionRef.current) {
        restartTimerRef.current = window.setTimeout(() => {
          restartTimerRef.current = null
          startRecognitionCycle(Recognition)
        }, 160)
        return
      }

      setVoiceStatus((current) => (current === 'listening' ? 'idle' : current))
    }

    try {
      recognition.start()
    } catch (recognitionError) {
      recognitionRef.current = null
      listeningSessionRef.current = false
      setVoiceStatus('error')
      setError(recognitionError instanceof Error ? recognitionError.message : String(recognitionError))
    }
  }

  async function stopListeningAndSend() {
    if (!listeningSessionRef.current && voiceStatus !== 'listening') return

    listeningSessionRef.current = false
    manualStopRef.current = true
    if (restartTimerRef.current !== null) {
      window.clearTimeout(restartTimerRef.current)
      restartTimerRef.current = null
    }

    const recognition = recognitionRef.current
    if (recognition) {
      try {
        recognition.stop()
        return
      } catch (stopError) {
        console.warn('Could not stop speech recognition cleanly:', stopError)
      }
    }

    manualStopRef.current = false
    await finalizeCapturedSpeech()
  }

  async function finalizeCapturedSpeech() {
    if (finalizeInFlightRef.current) return
    const transcript = capturedTranscriptRef.current.trim()
    capturedTranscriptRef.current = ''

    if (!transcript) {
      setVoiceStatus('idle')
      setError('还没有听到完整内容，请再次点击说话，讲完后再点击“停止说话”。')
      return
    }

    finalizeInFlightRef.current = true
    setLastTranscript(transcript)
    setVoiceStatus('processing')
    try {
      await runAction('chat', async () => handleUserMessage(transcript))
    } finally {
      finalizeInFlightRef.current = false
    }
  }

  function cancelListening() {
    listeningSessionRef.current = false
    manualStopRef.current = false
    capturedTranscriptRef.current = ''
    if (restartTimerRef.current !== null) {
      window.clearTimeout(restartTimerRef.current)
      restartTimerRef.current = null
    }
    const recognition = recognitionRef.current
    recognitionRef.current = null
    try {
      recognition?.abort()
    } catch (abortError) {
      console.warn('Could not abort speech recognition cleanly:', abortError)
    }
    setVoiceStatus((current) => (current === 'listening' ? 'idle' : current))
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
      cancelListening()
      const summary = buildSummary(profile, recommendedProducts)
      setSummaryText(summary)
      setScreenMode('summary')
      await sendDemoEvent('end', sessionId).catch(() => undefined)
      await speakText(`好的，我为您总结一下本次咨询。${summary}`)
    })
  }

  async function handleRestart() {
    await runAction('restart', async () => {
      cancelListening()
      stopSpeaking()
      await sendDemoEvent('end', sessionId).catch(() => undefined)
      setSessionId('demo-session-001')
      setProfile(INITIAL_PROFILE)
      setRecommendedProducts([])
      setMessages([])
      setInputText('')
      setCompareIds([])
      setCompareRows([])
      setSummaryText('')
      setLastTranscript('')
      setCompareOpen(false)
      setIdentityMessage('')
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
        <section className="welcome-screen agent-choice-mode">
          <div className="brand-mark">
            <Sparkles size={20} />
            <span>木地板 AI 选购顾问</span>
          </div>
          <ConsultantAvatar consultant={selectedConsultant} status="idle" large />
          <div className="welcome-copy">
            <p className="welcome-kicker">您好，我是小木 · {selectedConsultant.displayName}</p>
            <h1>帮您更轻松地选到合适的木地板</h1>
            <p>先选择您喜欢的导购风格，再告诉我房间、风格、预算和生活需求。</p>
          </div>

          <AgentPicker
            selectedId={selectedConsultantId}
            onSelect={(consultant) => void handleConsultantSelection(consultant, true)}
          />

          <button
            type="button"
            className="primary-cta"
            onClick={() => void handleStartConsultation()}
            disabled={busyAction !== null}
          >
            <Sparkles size={22} />
            {busyAction === 'start' ? '正在检查本地选购记忆…' : `和${selectedConsultant.displayName}开始咨询`}
          </button>
          <p className="privacy-note">
            摄像头画面不会显示。只有您明确同意后，才会在本机保存人脸特征和选购摘要；默认不保存原始照片。
          </p>
          {identityMessage && <p className="identity-inline-note">{identityMessage}</p>}
        </section>
      )}

      {screenMode === 'conversation' && (
        <section className="consultation-screen">
          <header className="customer-header">
            <div className="brand-title">
              <span className="mini-logo">
                <Sparkles size={17} />
              </span>
              <div>
                <strong>小木 · {selectedConsultant.displayName}</strong>
                <span>
                  {selectedConsultant.styleName} · {voiceStatusLabel(voiceStatus)}
                  {profile.is_returning_customer ? ' · 已确认回访记忆' : ''}
                </span>
              </div>
            </div>

            <AgentQuickSwitcher
              selectedId={selectedConsultantId}
              disabled={voiceStatus === 'listening' || busyAction !== null}
              onSelect={(consultant) => void handleConsultantSelection(consultant, true)}
            />

            <button
              type="button"
              className="quiet-button"
              onClick={() => void handleRestart()}
              disabled={busyAction !== null}
            >
              <RotateCcw size={17} />
              重新开始
            </button>
          </header>

          <div className="consultation-layout">
            <aside className="assistant-stage">
              <ConsultantAvatar consultant={selectedConsultant} status={avatarStatus} />
              <div className="assistant-status">
                <span className={`status-pulse ${avatarStatus}`} />
                <strong>{voiceStatusLabel(voiceStatus)}</strong>
                <p>
                  {voiceStatus === 'listening'
                    ? lastTranscript
                      ? `持续收音中：“${lastTranscript}”`
                      : '请继续说，全部讲完后点击“停止说话”。'
                    : lastTranscript
                      ? `刚刚听到：“${lastTranscript}”`
                      : '您可以直接说出需求，也可以输入文字。'}
                </p>
              </div>
              {profile.is_returning_customer && profile.memory_summary && (
                <div className="memory-context-card">
                  <strong>已确认的历史背景</strong>
                  <p>{profile.memory_summary}</p>
                </div>
              )}
              <div className="quick-start-list">
                {QUICK_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setInputText(prompt)}
                    disabled={busyAction !== null || voiceStatus === 'listening'}
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
                      <span>{message.role === 'agent' ? `小木 · ${selectedConsultant.displayName}` : '我'}</span>
                      <p>{message.text}</p>
                    </div>
                  </div>
                ))}
                {voiceStatus === 'processing' && (
                  <div className="message-row agent">
                    <div className="message-bubble thinking-bubble">
                      <span>小木 · {selectedConsultant.displayName}</span>
                      <p>
                        正在为您整理合适的建议<span className="typing-dots">•••</span>
                      </p>
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
                  placeholder={
                    voiceStatus === 'listening'
                      ? '正在持续收音，请说完后点击“停止说话”…'
                      : '例如：客厅用，家里有宠物，希望耐磨好清洁…'
                  }
                  rows={2}
                  disabled={voiceStatus === 'listening'}
                />
                <button
                  type="button"
                  className="send-button"
                  onClick={() => void handleTextSubmit()}
                  disabled={!inputText.trim() || busyAction !== null || voiceStatus === 'listening'}
                  aria-label="发送"
                >
                  <Send size={21} />
                </button>
              </div>

              <div className="primary-actions">
                <button
                  type="button"
                  className={`voice-button ${voiceStatus === 'listening' ? 'active' : ''}`}
                  onClick={() =>
                    voiceStatus === 'listening' ? void stopListeningAndSend() : void startListening()
                  }
                  disabled={!speechRecognitionSupported || (busyAction !== null && voiceStatus !== 'listening')}
                >
                  {voiceStatus === 'listening' ? <Square size={20} /> : <Mic size={22} />}
                  {voiceStatus === 'listening' ? '停止说话' : '点击说话'}
                </button>
                <button type="button" onClick={() => setCompareOpen(true)} disabled={products.length === 0}>
                  <BarChart3 size={21} />
                  产品对比
                </button>
                <button
                  type="button"
                  onClick={() => void handleFinishAndSummarize()}
                  disabled={busyAction !== null}
                >
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
            <div className="summary-icon">
              <ClipboardCheck size={30} />
            </div>
            <p>本次咨询已完成</p>
            <h1>您的选购要点</h1>
          </div>
          <div className="summary-grid">
            <SummaryItem label="铺装空间" value={profile.room_type ?? '尚未确认'} />
            <SummaryItem label="偏好风格" value={profile.style ?? '尚未确认'} />
            <SummaryItem label="预算区间" value={profile.budget ?? '尚未确认'} />
            <SummaryItem
              label="特殊需求"
              value={profile.special_needs.length ? profile.special_needs.join('、') : '暂无明确要求'}
            />
            <SummaryItem
              label="重点关注"
              value={profile.concerns.length ? profile.concerns.join('、') : '尚未确认'}
            />
            <SummaryItem
              label="推荐产品"
              value={
                recommendedProducts.length
                  ? recommendedProducts.map((product) => product.name).join('、')
                  : '需要继续了解需求'
              }
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

          <div className="local-memory-offer">
            <div>
              <strong>{profile.customer_id ? '本地选购记忆已保存' : '下次继续本次方案'}</strong>
              <p>
                {profile.customer_id
                  ? '系统已在本机保存人脸特征和选购摘要，未保存原始照片。'
                  : '经您明确同意后，系统只在本机保存人脸特征和本次摘要，下次可继续咨询。'}
              </p>
            </div>
            {!profile.customer_id && (
              <button type="button" onClick={() => setEnrollmentOpen(true)} disabled={busyAction !== null}>
                同意并保存本地记忆
              </button>
            )}
          </div>
          {identityMessage && <p className="identity-inline-note summary-note">{identityMessage}</p>}

          <div className="summary-actions">
            <button type="button" onClick={() => setScreenMode('conversation')}>
              继续咨询
            </button>
            <button
              type="button"
              className="primary-cta compact"
              onClick={() => void handleRestart()}
              disabled={busyAction !== null}
            >
              <RotateCcw size={20} />
              开始新的咨询
            </button>
          </div>
        </section>
      )}

      {identityPromptOpen && (
        <div className="modal-backdrop identity-backdrop" role="presentation">
          <section className="identity-modal" role="dialog" aria-modal="true" aria-label="确认历史客户记录">
            <div className="identity-symbol">
              <Sparkles size={28} />
            </div>
            <p className="identity-kicker">本地选购记忆</p>
            <h2>欢迎回来</h2>
            <p>{identityMessage || '我们可能找到了您之前同意保存的选购记录。'}</p>
            <p className="identity-safety-note">确认前不会显示姓名或历史内容，避免误认造成信息泄露。</p>
            <div className="identity-choice-grid">
              <button
                type="button"
                className="primary-cta compact"
                onClick={() => void handleIdentityChoice('continue_previous')}
                disabled={busyAction !== null}
              >
                继续上次咨询
              </button>
              <button
                type="button"
                onClick={() => void handleIdentityChoice('new_project')}
                disabled={busyAction !== null}
              >
                开始新的选购项目
              </button>
              <button
                type="button"
                className="quiet-button"
                onClick={() => void handleIdentityChoice('not_me')}
                disabled={busyAction !== null}
              >
                这不是我
              </button>
            </div>
          </section>
        </div>
      )}

      {enrollmentOpen && (
        <div className="modal-backdrop identity-backdrop" role="presentation">
          <section className="identity-modal enrollment-modal" role="dialog" aria-modal="true" aria-label="保存本地选购记忆">
            <button
              type="button"
              className="identity-close"
              onClick={() => setEnrollmentOpen(false)}
              aria-label="关闭"
            >
              <X size={20} />
            </button>
            <div className="identity-symbol">
              <Check size={28} />
            </div>
            <p className="identity-kicker">需要您的明确同意</p>
            <h2>保存本地选购记忆</h2>
            <p>请正对屏幕并保持光线充足。系统会在本机保存数个人脸特征向量和本次选购摘要，不保存原始人脸照片。</p>
            <label className="identity-name-field">
              <span>称呼（可选）</span>
              <input
                value={enrollmentName}
                onChange={(event) => setEnrollmentName(event.target.value)}
                placeholder="例如：王先生"
              />
            </label>
            <label className="identity-consent-row">
              <input
                type="checkbox"
                checked={enrollmentConsent}
                onChange={(event) => setEnrollmentConsent(event.target.checked)}
              />
              <span>我同意仅在本机保存人脸特征和本次选购记录，用于下次恢复咨询背景。</span>
            </label>
            <div className="identity-choice-grid">
              <button
                type="button"
                className="primary-cta compact"
                onClick={() => void handleEnrollment()}
                disabled={!enrollmentConsent || busyAction !== null}
              >
                {busyAction === 'enroll' ? '正在采集清晰人脸…' : '同意并开始采集'}
              </button>
              <button type="button" onClick={() => setEnrollmentOpen(false)} disabled={busyAction !== null}>
                暂不保存
              </button>
            </div>
          </section>
        </div>
      )}

      {compareOpen && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setCompareOpen(false)}>
          <section
            className="compare-modal"
            role="dialog"
            aria-modal="true"
            aria-label="产品对比"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <p>最多选择两款</p>
                <h2>产品对比</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                onClick={() => setCompareOpen(false)}
                aria-label="关闭产品对比"
              >
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
    listening: '正在持续听您说',
    processing: '正在整理建议',
    speaking: '正在为您讲解',
    error: '请再试一次',
  }
  return labels[status]
}

function AgentPicker({
  selectedId,
  onSelect,
}: {
  selectedId: ConsultantId
  onSelect: (consultant: ConsultantProfile) => void
}) {
  return (
    <section className="agent-picker" aria-label="选择 AI 导购风格">
      <div className="agent-picker-heading">
        <strong>选择您喜欢的导购风格</strong>
        <span>点击人像即可选择并试听</span>
      </div>
      <div className="agent-choice-grid">
        {CONSULTANTS.map((consultant) => {
          const selected = consultant.id === selectedId
          return (
            <button
              key={consultant.id}
              type="button"
              className={`agent-choice-card ${selected ? 'selected' : ''}`}
              onClick={() => onSelect(consultant)}
              aria-pressed={selected}
            >
              <ConsultantAvatar consultant={consultant} status="idle" mini />
              <span className="agent-choice-name">{consultant.displayName}</span>
              <strong>{consultant.styleName}</strong>
              <small>{consultant.description}</small>
              <span className="agent-choice-state">{selected ? '已选择' : '选择并试听'}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function AgentQuickSwitcher({
  selectedId,
  disabled,
  onSelect,
}: {
  selectedId: ConsultantId
  disabled: boolean
  onSelect: (consultant: ConsultantProfile) => void
}) {
  return (
    <div className="agent-quick-switcher" aria-label="更换导购风格">
      <span>更换导购</span>
      <div>
        {CONSULTANTS.map((consultant) => (
          <button
            key={consultant.id}
            type="button"
            className={consultant.id === selectedId ? 'selected' : ''}
            onClick={() => onSelect(consultant)}
            disabled={disabled}
            title={`${consultant.displayName} · ${consultant.styleName}`}
            aria-label={`选择${consultant.displayName}，${consultant.styleName}`}
            aria-pressed={consultant.id === selectedId}
          >
            <ConsultantAvatar consultant={consultant} status="idle" mini />
          </button>
        ))}
      </div>
    </div>
  )
}

function ConsultantAvatar({
  consultant,
  status,
  large = false,
  mini = false,
}: {
  consultant: ConsultantProfile
  status: VoiceStatus
  large?: boolean
  mini?: boolean
}) {
  const shirtGradientId = `shirt-gradient-${consultant.id}`
  const hairGradientId = `hair-gradient-${consultant.id}`
  const hairPath =
    consultant.accessory === 'young'
      ? 'M72 119C62 69 85 25 128 20c47-5 75 29 67 91-13-15-31-27-53-34-16 20-37 31-65 30-1 6-3 10-5 12z'
      : consultant.accessory === 'mature'
        ? 'M74 119C65 67 88 25 137 23c42-2 65 33 56 92-13-7-23-20-29-37-19 20-45 29-82 27-1 7-4 12-8 14z'
        : consultant.accessory === 'glasses'
          ? 'M74 118C63 64 87 22 134 21c45-1 68 34 58 96-14-8-24-23-28-39-19 21-45 30-82 27-1 6-4 11-8 13z'
          : 'M74 120C61 61 88 18 137 18c44 0 68 35 57 99-12-6-21-22-24-38-20 22-49 30-87 27-1 8-4 12-9 14z'

  return (
    <div
      className={`consultant-avatar ${status} ${large ? 'large' : ''} ${mini ? 'mini' : ''}`}
      aria-label={`AI 导购小木，${consultant.displayName}，${consultant.styleName}`}
    >
      <div className="avatar-halo" />
      <svg viewBox="0 0 260 300" role="img" aria-hidden="true">
        <defs>
          <linearGradient id={shirtGradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={consultant.shirtStart} />
            <stop offset="100%" stopColor={consultant.shirtEnd} />
          </linearGradient>
          <linearGradient id={hairGradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={consultant.hairStart} />
            <stop offset="100%" stopColor={consultant.hairEnd} />
          </linearGradient>
        </defs>
        <ellipse cx="130" cy="279" rx="91" ry="17" fill="rgba(56,35,25,.12)" />
        <path d="M51 282c8-56 38-85 79-85s72 29 80 85" fill={`url(#${shirtGradientId})`} />
        <path d="M104 199h52v39c-8 13-44 13-52 0z" fill={consultant.skin} />
        <path
          d="M78 111c0-55 24-85 56-85 42 0 61 34 56 88l-10 59c-8 36-28 54-50 54s-43-18-51-54z"
          fill={consultant.skin}
        />
        <path d={hairPath} fill={`url(#${hairGradientId})`} />
        {consultant.accessory === 'young' && (
          <path
            d="M83 83c13-24 35-39 64-43 20-3 34 2 45 13-19-4-35 1-49 15-18-8-38-3-60 15z"
            fill={consultant.hairStart}
            opacity=".92"
          />
        )}
        {consultant.accessory === 'mature' && (
          <>
            <path
              d="M83 83c5-25 23-43 49-50"
              stroke="#a69b94"
              strokeWidth="7"
              strokeLinecap="round"
              opacity=".75"
            />
            <path
              d="M181 73c8 14 11 31 8 50"
              stroke="#817873"
              strokeWidth="6"
              strokeLinecap="round"
              opacity=".7"
            />
          </>
        )}
        <path d="M78 113c-14 2-17 17-10 32 4 9 10 14 17 13" fill={consultant.skin} />
        <path d="M185 113c14 2 17 17 10 32-4 9-10 14-17 13" fill={consultant.skin} />
        <path
          d="M103 130c7-5 15-5 22 0"
          stroke="#5b3c31"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
        <path
          d="M142 130c7-5 15-5 22 0"
          stroke="#5b3c31"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
        <ellipse cx="114" cy="137" rx="4" ry="5" fill="#34231f" />
        <ellipse cx="153" cy="137" rx="4" ry="5" fill="#34231f" />
        {consultant.accessory === 'glasses' && (
          <>
            <rect
              x="96"
              y="126"
              width="34"
              height="25"
              rx="10"
              fill="none"
              stroke="#3b454e"
              strokeWidth="3"
            />
            <rect
              x="138"
              y="126"
              width="34"
              height="25"
              rx="10"
              fill="none"
              stroke="#3b454e"
              strokeWidth="3"
            />
            <path d="M130 137h8" stroke="#3b454e" strokeWidth="3" />
          </>
        )}
        <path
          d="M132 142c-3 10-4 17 3 20"
          stroke="#d69c7d"
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
        />
        {consultant.accessory === 'mature' && (
          <path
            d="M117 169c9-5 23-5 32 0"
            stroke="#5e4a43"
            strokeWidth="3"
            strokeLinecap="round"
            opacity=".65"
          />
        )}
        <path
          className="avatar-mouth"
          d="M115 177c11 9 25 9 37 0"
          stroke="#9a4b4c"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
        <path d="M99 207l31 25 31-25 15 17-18 58H102l-18-58z" fill="#f8f4ef" />
        <path d="M130 232v50" stroke="#d6c6b7" strokeWidth="3" />
        <circle cx="130" cy="252" r="4" fill={consultant.shirtStart} />
        {consultant.accessory === 'glasses' && (
          <path d="M130 232l-7 18 7 17 7-17z" fill="#455969" />
        )}
        {consultant.accessory === 'mature' && (
          <path d="M130 232l-8 22 8 20 8-20z" fill="#6f5547" />
        )}
      </svg>
      <div className="voice-rings">
        <span />
        <span />
        <span />
      </div>
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
        <p>
          {product.type} · {product.price_range} · {product.wear_level}
        </p>
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
