(() => {
  if (!document.querySelector('script[data-woodfloor-dynamic-i18n]')) {
    const script = document.createElement('script')
    script.src = '/bilingual-dynamic.js'
    script.dataset.woodfloorDynamicI18n = 'true'
    document.head.appendChild(script)
  }

  const voiceMap = {
    zm_yunxi: 'am_liam',
    zm_yunjian: 'am_michael',
    zm_yunxia: 'am_puck',
    zm_yunyang: 'am_onyx'
  }

  const productNames = {
    'WF-SPC-001': 'Light Grey Spruce SPC Click Flooring',
    'WF-WOOD-002': 'Natural Oak Engineered Wood Flooring',
    'WF-LAM-003': 'Morning Mist Grey Laminate Flooring',
    'WF-SPC-004': 'Dark Walnut Waterproof SPC Flooring',
    'WF-WOOD-005': 'Warm Light Oak Three-Layer Wood Flooring',
    'WF-LAM-006': 'Cream White High-Wear Laminate Flooring'
  }

  const englishSpeechText = {
    '您好，我是温暖亲和风格的导购小木，很高兴为您服务。': 'Hello, I am Xiao Mu in the warm and friendly consultant style. It is a pleasure to help you.',
    '您好，我是沉稳专业风格的导购小木，我会为您清晰比较产品特点。': 'Hello, I am Xiao Mu in the calm and professional consultant style. I will compare the product differences clearly.',
    '您好，我是年轻活力风格的导购小木，我们一起找到更适合您家的方案。': 'Hello, I am Xiao Mu in the young and energetic consultant style. Let us find the right option for your home.',
    '您好，我是成熟自信风格的导购小木，我会帮您抓住选购重点。': 'Hello, I am Xiao Mu in the mature and confident consultant style. I will help you focus on the key buying criteria.'
  }

  const chineseProductNames = {
    '云杉浅灰 SPC 锁扣地板': 'Light Grey Spruce SPC Click Flooring',
    '原木橡木多层实木地板': 'Natural Oak Engineered Wood Flooring',
    '晨雾灰强化复合地板': 'Morning Mist Grey Laminate Flooring',
    '深胡桃防水 SPC 地板': 'Dark Walnut Waterproof SPC Flooring',
    '温润浅橡三层实木地板': 'Warm Light Oak Three-Layer Wood Flooring',
    '奶油白高耐磨强化地板': 'Cream White High-Wear Laminate Flooring'
  }

  const chineseSpeechTerms = {
    '耐磨易维护': 'durable and easy-care',
    '地暖适配': 'suitable for underfloor heating',
    '高品质实木质感': 'premium natural wood character',
    '经济实用': 'value-focused and practical',
    '强化复合地板': 'laminate flooring',
    '多层实木地板': 'engineered wood flooring',
    '三层实木地板': 'three-layer wood flooring',
    '锁扣地板': 'click flooring',
    '主推款': 'main recommendation',
    '备选款': 'backup option',
    '对比款': 'comparison option',
    '浅灰色': 'light grey',
    '深胡桃色': 'dark walnut',
    '原木色': 'natural oak',
    '奶油白': 'cream white',
    '现代简约': 'modern minimalist',
    '新中式': 'contemporary Chinese style',
    '客厅': 'living room',
    '卧室': 'bedroom',
    '全屋': 'whole home',
    '耐磨': 'wear resistance',
    '防水': 'water resistance',
    '脚感': 'underfoot feel',
    '环保': 'environmental documentation',
    '好清洁': 'easy cleaning',
    '地暖': 'underfloor heating',
    '宠物': 'pets',
    '预算': 'budget',
    '中等': 'mid-range',
    '偏高': 'upper-mid range',
    '高端': 'premium',
    '经济': 'economy'
  }

  function language() {
    return window.__WOODFLOOR_LANGUAGE__ === 'en' || window.localStorage.getItem('woodfloor_ui_language') === 'en'
      ? 'en'
      : 'zh'
  }

  function requestUrl(input) {
    if (typeof input === 'string') return input
    if (input instanceof URL) return input.toString()
    return input && typeof input.url === 'string' ? input.url : ''
  }

  function containsChinese(value) {
    return typeof value === 'string' && /[\u4e00-\u9fff]/.test(value)
  }

  function translateSummary(text) {
    const source = String(text || '')
      .replace(/^好的，我为您总结一下本次咨询。/, '')
      .replace(/。$/, '')
    const labels = {
      '铺装空间': 'Room',
      '偏好风格': 'Preferred style',
      '预算区间': 'Budget range',
      '特殊需求': 'Special requirements',
      '重点关注': 'Key priorities',
      '推荐产品': 'Recommended products'
    }
    const translated = source
      .split('；')
      .map((part) => {
        const separator = part.indexOf('：')
        if (separator < 0) return part
        const label = part.slice(0, separator)
        const value = part.slice(separator + 1)
        return `${labels[label] || label}: ${value}`
      })
      .join('; ')
    return translated
      ? `Let me summarise this consultation. ${translated}.`
      : 'Let me summarise this consultation for you.'
  }

  function sanitizeEnglishSpeechText(value) {
    let text = String(value || '').trim()
    if (!text) return 'Let me continue with the selected flooring options.'
    if (englishSpeechText[text]) text = englishSpeechText[text]
    if (text.startsWith('好的，我为您总结一下本次咨询。')) text = translateSummary(text)

    for (const [source, target] of Object.entries(chineseProductNames)) {
      text = text.split(source).join(target)
    }
    const terms = Object.entries(chineseSpeechTerms).sort((left, right) => right[0].length - left[0].length)
    for (const [source, target] of terms) {
      text = text.split(source).join(target)
    }

    // English Kokoro voices can pronounce residual Han characters as the literal
    // phrase “Chinese letter”. Never send unresolved CJK characters to an English
    // voice. Known retail terms are translated above; unknown fragments are removed
    // rather than spoken incorrectly.
    text = text
      .replace(/[\u3400-\u4dbf\u4e00-\u9fff]+/g, ' ')
      .replace(/[，。！？；：“”‘’、]/g, ' ')
      .replace(/\s+/g, ' ')
      .replace(/\s+([,.;:!?])/g, '$1')
      .trim()

    if (!/[A-Za-z]/.test(text) || text.length < 8) {
      return 'Let me continue with the selected flooring options and explain the practical differences.'
    }
    return text
  }

  function englishChatFallback(payload) {
    const products = Array.isArray(payload.recommended_products) ? payload.recommended_products : []
    if (products.length) {
      const main = productNames[products[0]?.id] || `Product ${products[0]?.id || ''}`.trim()
      const backup = products[1] ? productNames[products[1].id] || `Product ${products[1].id}` : null
      let answer = `Based on the confirmed requirements, my main recommendation is ${main}.`
      if (backup) answer += ` The backup option is ${backup}, which gives you a second material, appearance or budget direction to compare.`
      answer += ' The final choice should still balance performance, underfoot feel, maintenance and budget. You can take your time and share any one detail when you are ready.'
      return answer
    }
    if (String(payload.answer || '').includes('Qwen')) {
      return 'The local Qwen service is temporarily unavailable. Confirm that Ollama is running with qwen3.5:4b loaded, then try again.'
    }
    if (String(payload.answer || '').includes('云端')) {
      return 'The cloud intelligence service is temporarily unavailable. This session will not silently switch to another model. Please try again later.'
    }
    return 'Understood. I have recorded the information you confirmed. I will continue from the current context without restarting a questionnaire.'
  }

  async function localizeResponse(url, response) {
    if (language() !== 'en' || !url.includes('/api/chat')) return response
    const contentType = response.headers.get('content-type') || ''
    if (!contentType.includes('application/json')) return response
    try {
      const payload = await response.clone().json()
      if (!containsChinese(payload.answer)) return response
      payload.answer = englishChatFallback(payload)
      const headers = new Headers(response.headers)
      headers.set('content-type', 'application/json; charset=utf-8')
      return new Response(JSON.stringify(payload), {
        status: response.status,
        statusText: response.statusText,
        headers
      })
    } catch {
      return response
    }
  }

  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = requestUrl(input)
    if (language() !== 'en' || !init || typeof init.body !== 'string') {
      return localizeResponse(url, await originalFetch(input, init))
    }

    let body
    try {
      body = JSON.parse(init.body)
    } catch {
      return localizeResponse(url, await originalFetch(input, init))
    }

    if (url.includes('/api/chat')) body.response_language = 'en'

    if (url.includes('/api/tts')) {
      body.language = 'en'
      if (typeof body.voice === 'string' && voiceMap[body.voice]) body.voice = voiceMap[body.voice]
      if (typeof body.text === 'string') body.text = sanitizeEnglishSpeechText(body.text)
    }

    if (url.includes('/api/identity/')) body.response_language = 'en'

    const response = await originalFetch(input, { ...init, body: JSON.stringify(body) })
    return localizeResponse(url, response)
  }
})()
