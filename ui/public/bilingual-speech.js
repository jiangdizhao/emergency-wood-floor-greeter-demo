(() => {
  if (!window.speechSynthesis || window.__WOODFLOOR_ENGLISH_SPEECH_TEXT_GUARD__) return

  const exact = {
    '您好，我是温暖亲和风格的导购小木，很高兴为您服务。': 'Hello, I am Xiao Mu in the warm and friendly consultant style. It is a pleasure to help you.',
    '您好，我是沉稳专业风格的导购小木，我会为您清晰比较产品特点。': 'Hello, I am Xiao Mu in the calm and professional consultant style. I will compare the product differences clearly.',
    '您好，我是年轻活力风格的导购小木，我们一起找到更适合您家的方案。': 'Hello, I am Xiao Mu in the young and energetic consultant style. Let us find the right option for your home.',
    '您好，我是成熟自信风格的导购小木，我会帮您抓住选购重点。': 'Hello, I am Xiao Mu in the mature and confident consultant style. I will help you focus on the key buying criteria.'
  }

  function isEnglish() {
    return window.__WOODFLOOR_LANGUAGE__ === 'en' || window.localStorage.getItem('woodfloor_ui_language') === 'en'
  }

  function translateSummary(text) {
    const labels = {
      '铺装空间': 'Room',
      '偏好风格': 'Preferred style',
      '预算区间': 'Budget range',
      '特殊需求': 'Special requirements',
      '重点关注': 'Key priorities',
      '推荐产品': 'Recommended products'
    }
    const source = String(text || '')
      .replace(/^好的，我为您总结一下本次咨询。/, '')
      .replace(/。$/, '')
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
    return translated ? `Let me summarise this consultation. ${translated}.` : 'Let me summarise this consultation for you.'
  }

  function translate(text) {
    if (!isEnglish()) return text
    if (exact[text]) return exact[text]
    if (String(text).startsWith('好的，我为您总结一下本次咨询。')) return translateSummary(text)
    if (/[\u4e00-\u9fff]/.test(String(text))) {
      return 'Understood. I have recorded the information you confirmed. Which one point would you like to discuss next?'
    }
    return text
  }

  const previousSpeak = window.speechSynthesis.speak.bind(window.speechSynthesis)
  window.speechSynthesis.speak = (utterance) => {
    if (isEnglish()) {
      utterance.lang = 'en-US'
      utterance.text = translate(utterance.text)
    }
    previousSpeak(utterance)
  }
  window.__WOODFLOOR_ENGLISH_SPEECH_TEXT_GUARD__ = true
})()
