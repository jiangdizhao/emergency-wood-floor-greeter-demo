(() => {
  function isEnglish() {
    return window.__WOODFLOOR_LANGUAGE__ === 'en' || window.localStorage.getItem('woodfloor_ui_language') === 'en'
  }

  const summaryLabels = {
    '铺装空间': 'Room',
    '偏好风格': 'Preferred style',
    '预算区间': 'Budget range',
    '特殊需求': 'Special requirements',
    '重点关注': 'Key priorities',
    '推荐产品': 'Recommended products'
  }

  function translateDynamicText(value) {
    if (!isEnglish() || typeof value !== 'string') return value
    const trimmed = value.trim()
    if (!trimmed.includes('铺装空间：') || !trimmed.includes('推荐产品：')) return value
    const leading = value.match(/^\s*/)?.[0] || ''
    const trailing = value.match(/\s*$/)?.[0] || ''
    const translated = trimmed
      .replace(/。$/, '')
      .split('；')
      .map((part) => {
        const separator = part.indexOf('：')
        if (separator < 0) return part
        const label = part.slice(0, separator)
        const content = part.slice(separator + 1)
        return `${summaryLabels[label] || label}: ${content}`
      })
      .join('; ')
    return `${leading}${translated}.${trailing}`
  }

  function process(root) {
    if (!isEnglish()) return
    if (root.nodeType === Node.TEXT_NODE) {
      const translated = translateDynamicText(root.nodeValue || '')
      if (translated !== root.nodeValue) root.nodeValue = translated
      return
    }
    if (!(root instanceof Element) && root !== document) return
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
    let node = walker.nextNode()
    while (node) {
      const translated = translateDynamicText(node.nodeValue || '')
      if (translated !== node.nodeValue) node.nodeValue = translated
      node = walker.nextNode()
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    process(document.body)
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === 'characterData') process(record.target)
        for (const node of record.addedNodes) process(node)
      }
    })
    observer.observe(document.body, { subtree: true, childList: true, characterData: true })
  })
})()
