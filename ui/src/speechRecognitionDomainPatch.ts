import {
  RealtimeRecognition,
  realtimeAsrSelected,
  type RecognitionErrorEvent,
  type RecognitionEvent,
  type RecognitionLike,
} from './realtimeSpeechRecognition'

type NativeAlternative = {
  transcript: string
  confidence?: number
}

type NativeResult = {
  isFinal?: boolean
  length: number
  [index: number]: NativeAlternative
}

type NativeEvent = {
  results: {
    length: number
    [index: number]: NativeResult
  }
}

type NativeRecognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onstart: (() => void) | null
  onend: (() => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onresult: ((event: NativeEvent) => void) | null
}

type NativeRecognitionConstructor = new () => NativeRecognition

const ASR_PROVIDER_KEY = 'woodfloor_asr_provider'
const BROWSER_PROVIDER = 'browser'

const ZH_DOMAIN_TERMS = [
  '浅灰色',
  '浅灰',
  '深灰色',
  '灰色',
  '原木色',
  '深色系',
  '现代简约',
  '北欧',
  '新中式',
  '轻奢',
  '客厅',
  '卧室',
  '全屋',
  '经济',
  '中等',
  '偏高',
  '高端',
  '防水',
  '耐磨',
  '环保',
  '价格',
  '脚感',
  '好清洁',
  '地暖',
  '宠物',
  'SPC',
  '多层实木',
  '强化地板',
]

const EN_DOMAIN_TERMS = [
  'light grey',
  'natural oak',
  'dark walnut',
  'modern minimalist',
  'Scandinavian',
  'contemporary Chinese',
  'living room',
  'bedroom',
  'whole home',
  'economy',
  'mid-range',
  'premium',
  'water resistance',
  'waterproof',
  'wear resistance',
  'durable',
  'environmental documentation',
  'budget',
  'underfoot feel',
  'easy to clean',
  'underfloor heating',
  'pets',
  'SPC',
  'engineered wood',
  'laminate',
  'square metres',
  'square meters',
]

const COMMON_BAD_SHORT_FORMS = new Set(['钱', '灰', '浅', '原', '中', '高', '低'])

function selectedLanguage(): 'zh' | 'en' {
  const configured = (window as Window & { __WOODFLOOR_LANGUAGE__?: string }).__WOODFLOOR_LANGUAGE__
  return configured === 'en' || window.localStorage.getItem('woodfloor_ui_language') === 'en' ? 'en' : 'zh'
}

function candidateScore(candidate: NativeAlternative): number {
  const text = candidate.transcript.replace(/\s+/g, ' ').trim()
  const normalized = selectedLanguage() === 'en' ? text.toLowerCase() : text.replace(/\s+/g, '')
  if (!normalized) return Number.NEGATIVE_INFINITY

  const terms = selectedLanguage() === 'en' ? EN_DOMAIN_TERMS : ZH_DOMAIN_TERMS
  let score = (candidate.confidence ?? 0) * 4
  for (const term of terms) {
    const comparableTerm = selectedLanguage() === 'en' ? term.toLowerCase() : term
    if (normalized === comparableTerm) score += 20
    else if (normalized.includes(comparableTerm)) score += 8
  }

  if (selectedLanguage() === 'zh' && COMMON_BAD_SHORT_FORMS.has(normalized)) score -= 8
  if (normalized.length >= 2) score += 1
  return score
}

function rankEvent(event: NativeEvent): NativeEvent {
  const rankedResults: NativeResult[] = []

  for (let resultIndex = 0; resultIndex < event.results.length; resultIndex += 1) {
    const nativeResult = event.results[resultIndex]
    const alternatives = Array.from(
      { length: nativeResult.length },
      (_, alternativeIndex) => nativeResult[alternativeIndex],
    )
      .filter(Boolean)
      .sort((left, right) => candidateScore(right) - candidateScore(left))

    const snapshot = alternatives as NativeResult
    snapshot.isFinal = nativeResult.isFinal
    rankedResults.push(snapshot)
  }

  return { results: rankedResults }
}

function installDomainRecognitionPatch() {
  const speechWindow = window as Window & {
    SpeechRecognition?: NativeRecognitionConstructor
    webkitSpeechRecognition?: NativeRecognitionConstructor
    __flooringSpeechPatchInstalled?: boolean
  }

  if (speechWindow.__flooringSpeechPatchInstalled) return
  const Original = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition
  const NativeRecognitionClass: NativeRecognitionConstructor | null = Original ?? null

  class DomainRecognition implements NativeRecognition {
    private readonly nativeRecognition: NativeRecognition
    private resultHandler: ((event: NativeEvent) => void) | null = null

    constructor() {
      if (!NativeRecognitionClass) throw new Error('Browser SpeechRecognition is unavailable.')
      this.nativeRecognition = new NativeRecognitionClass()
      this.nativeRecognition.maxAlternatives = 3
      this.nativeRecognition.lang = selectedLanguage() === 'en' ? 'en-US' : 'zh-CN'
    }

    get lang() {
      return this.nativeRecognition.lang
    }

    set lang(_value: string) {
      this.nativeRecognition.lang = selectedLanguage() === 'en' ? 'en-US' : 'zh-CN'
    }

    get continuous() {
      return this.nativeRecognition.continuous
    }

    set continuous(value: boolean) {
      this.nativeRecognition.continuous = value
    }

    get interimResults() {
      return this.nativeRecognition.interimResults
    }

    set interimResults(value: boolean) {
      this.nativeRecognition.interimResults = value
    }

    get maxAlternatives() {
      return this.nativeRecognition.maxAlternatives
    }

    set maxAlternatives(value: number) {
      this.nativeRecognition.maxAlternatives = Math.max(3, Number(value) || 1)
    }

    get onstart() {
      return this.nativeRecognition.onstart
    }

    set onstart(value: (() => void) | null) {
      this.nativeRecognition.onstart = value
    }

    get onend() {
      return this.nativeRecognition.onend
    }

    set onend(value: (() => void) | null) {
      this.nativeRecognition.onend = value
    }

    get onerror() {
      return this.nativeRecognition.onerror
    }

    set onerror(value: ((event: RecognitionErrorEvent) => void) | null) {
      this.nativeRecognition.onerror = value
    }

    get onresult() {
      return this.resultHandler
    }

    set onresult(value: ((event: NativeEvent) => void) | null) {
      this.resultHandler = value
      this.nativeRecognition.onresult = value ? (event: NativeEvent) => value(rankEvent(event)) : null
    }

    start() {
      this.nativeRecognition.lang = selectedLanguage() === 'en' ? 'en-US' : 'zh-CN'
      this.nativeRecognition.start()
    }

    stop() {
      this.nativeRecognition.stop()
    }

    abort() {
      this.nativeRecognition.abort()
    }
  }

  class AdaptiveRecognition implements NativeRecognition {
    lang = selectedLanguage() === 'en' ? 'en-US' : 'zh-CN'
    continuous = true
    interimResults = true
    maxAlternatives = 1
    onstart: (() => void) | null = null
    onend: (() => void) | null = null
    onerror: ((event: RecognitionErrorEvent) => void) | null = null
    onresult: ((event: NativeEvent) => void) | null = null

    private delegate: NativeRecognition | RecognitionLike | null = null
    private fallbackStarted = false
    private realtimeStarted = false

    start() {
      try {
        const realtimeSelected = realtimeAsrSelected()
        const delegate = realtimeSelected ? new RealtimeRecognition() : new DomainRecognition()
        this.delegate = delegate
        this.bindDelegate(delegate, realtimeSelected)
        delegate.start()
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        queueMicrotask(() => {
          this.onerror?.({ error: 'service-not-allowed', message })
          this.onend?.()
        })
      }
    }

    stop() {
      this.delegate?.stop()
    }

    abort() {
      this.delegate?.abort()
    }

    private bindDelegate(delegate: NativeRecognition | RecognitionLike, realtimeDelegate: boolean) {
      delegate.lang = this.lang
      delegate.continuous = this.continuous
      delegate.interimResults = this.interimResults
      delegate.maxAlternatives = this.maxAlternatives
      delegate.onstart = () => {
        if (realtimeDelegate) this.realtimeStarted = true
        this.onstart?.()
      }
      delegate.onresult = this.onresult as ((event: RecognitionEvent) => void) | null
      delegate.onerror = (event) => {
        const canFallback =
          realtimeDelegate &&
          !this.fallbackStarted &&
          ['network', 'service-not-allowed', 'audio-capture'].includes(event.error) &&
          NativeRecognitionClass

        if (!canFallback) {
          this.onerror?.(event)
          return
        }

        localStorage.setItem(ASR_PROVIDER_KEY, BROWSER_PROVIDER)
        window.dispatchEvent(
          new CustomEvent('woodfloor:asr-provider-fallback', {
            detail: {
              from: 'gpt-realtime-2',
              to: BROWSER_PROVIDER,
              reason: event.message ?? event.error,
              deferred: this.realtimeStarted,
            },
          }),
        )

        // Before onstart there is no user audio to preserve, so Browser ASR can
        // take over immediately. After an active turn has already started, opening
        // Browser ASR after the user pressed Stop would be surprising and could
        // record a new unintended turn. In that case switch the next turn only.
        if (this.realtimeStarted) {
          this.onerror?.(event)
          return
        }

        this.fallbackStarted = true
        const browserDelegate = new DomainRecognition()
        this.delegate = browserDelegate
        this.bindDelegate(browserDelegate, false)
        try {
          browserDelegate.start()
        } catch (fallbackError) {
          this.onerror?.({
            error: 'service-not-allowed',
            message: fallbackError instanceof Error ? fallbackError.message : String(fallbackError),
          })
          this.onend?.()
        }
      }
      delegate.onend = () => {
        if (realtimeDelegate && this.fallbackStarted) return
        this.onend?.()
      }
    }
  }

  speechWindow.SpeechRecognition = AdaptiveRecognition
  speechWindow.webkitSpeechRecognition = AdaptiveRecognition
  speechWindow.__flooringSpeechPatchInstalled = true
}

installDomainRecognitionPatch()
