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

const DOMAIN_TERMS = [
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

const COMMON_BAD_SHORT_FORMS = new Set(['钱', '灰', '浅', '原', '中', '高', '低'])

function candidateScore(candidate: NativeAlternative): number {
  const text = candidate.transcript.replace(/\s+/g, '').trim()
  if (!text) return Number.NEGATIVE_INFINITY

  let score = (candidate.confidence ?? 0) * 4
  for (const term of DOMAIN_TERMS) {
    if (text === term) score += 20
    else if (text.includes(term)) score += 8
  }

  if (COMMON_BAD_SHORT_FORMS.has(text)) score -= 8
  if (text.length >= 2) score += 1
  return score
}

function rankResult(result: NativeResult): NativeResult {
  const alternatives = Array.from({ length: result.length }, (_, index) => result[index]).filter(Boolean)
  alternatives.sort((left, right) => candidateScore(right) - candidateScore(left))

  return new Proxy(result, {
    get(target, property, receiver) {
      if (property === 'length') return alternatives.length
      if (typeof property === 'string' && /^\d+$/.test(property)) {
        return alternatives[Number(property)]
      }
      return Reflect.get(target, property, receiver)
    },
  })
}

function rankEvent(event: NativeEvent): NativeEvent {
  const results = new Proxy(event.results, {
    get(target, property, receiver) {
      if (typeof property === 'string' && /^\d+$/.test(property)) {
        const result = Reflect.get(target, property, receiver) as NativeResult
        return result ? rankResult(result) : result
      }
      return Reflect.get(target, property, receiver)
    },
  })

  return new Proxy(event, {
    get(target, property, receiver) {
      if (property === 'results') return results
      return Reflect.get(target, property, receiver)
    },
  })
}

function installDomainRecognitionPatch() {
  const speechWindow = window as Window & {
    SpeechRecognition?: new () => Record<string, unknown>
    webkitSpeechRecognition?: new () => Record<string, unknown>
    __flooringSpeechPatchInstalled?: boolean
  }

  if (speechWindow.__flooringSpeechPatchInstalled) return
  const Original = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition
  if (!Original) return

  const Wrapped = new Proxy(Original, {
    construct(target, args, newTarget) {
      const nativeRecognition = Reflect.construct(target, args, newTarget) as Record<string, unknown>
      const proxy = new Proxy(nativeRecognition, {
        set(instance, property, value, receiver) {
          if (property === 'maxAlternatives') {
            return Reflect.set(instance, property, Math.max(3, Number(value) || 1), receiver)
          }
          if (property === 'onresult' && typeof value === 'function') {
            const wrappedHandler = (event: NativeEvent) => value(rankEvent(event))
            return Reflect.set(instance, property, wrappedHandler, receiver)
          }
          return Reflect.set(instance, property, value, receiver)
        },
      })
      Reflect.set(nativeRecognition, 'maxAlternatives', 3)
      return proxy
    },
  })

  speechWindow.SpeechRecognition = Wrapped
  speechWindow.webkitSpeechRecognition = Wrapped
  speechWindow.__flooringSpeechPatchInstalled = true
}

installDomainRecognitionPatch()
