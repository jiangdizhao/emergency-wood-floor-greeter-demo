(() => {
  const voiceMap = {
    zm_yunxi: 'am_liam',
    zm_yunjian: 'am_michael',
    zm_yunxia: 'am_puck',
    zm_yunyang: 'am_onyx'
  }

  const englishSpeechText = {
    '您好，我是温暖亲和风格的导购小木，很高兴为您服务。': 'Hello, I am Xiao Mu in the warm and friendly consultant style. It is a pleasure to help you.',
    '您好，我是沉稳专业风格的导购小木，我会为您清晰比较产品特点。': 'Hello, I am Xiao Mu in the calm and professional consultant style. I will compare the product differences clearly.',
    '您好，我是年轻活力风格的导购小木，我们一起找到更适合您家的方案。': 'Hello, I am Xiao Mu in the young and energetic consultant style. Let us find the right option for your home.',
    '您好，我是成熟自信风格的导购小木，我会帮您抓住选购重点。': 'Hello, I am Xiao Mu in the mature and confident consultant style. I will help you focus on the key buying criteria.',
    '好的，我为您总结一下本次咨询。': 'Let me summarise this consultation for you.'
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

  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    if (language() !== 'en' || !init || typeof init.body !== 'string') {
      return originalFetch(input, init)
    }

    const url = requestUrl(input)
    let body
    try {
      body = JSON.parse(init.body)
    } catch {
      return originalFetch(input, init)
    }

    if (url.includes('/api/chat')) {
      body.response_language = 'en'
    }

    if (url.includes('/api/tts')) {
      body.language = 'en'
      if (typeof body.voice === 'string' && voiceMap[body.voice]) body.voice = voiceMap[body.voice]
      if (typeof body.text === 'string' && englishSpeechText[body.text]) body.text = englishSpeechText[body.text]
      if (typeof body.text === 'string' && body.text.startsWith('好的，我为您总结一下本次咨询。')) {
        body.text = 'Let me summarise this consultation for you.'
      }
    }

    if (url.includes('/api/identity/')) {
      body.response_language = 'en'
    }

    return originalFetch(input, { ...init, body: JSON.stringify(body) })
  }
})()
