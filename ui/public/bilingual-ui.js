(() => {
  const STORAGE_KEY = 'woodfloor_ui_language'
  const LANGUAGE_EVENT = 'woodfloor-language-change'
  const supported = new Set(['zh', 'en'])

  function readLanguage() {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    return supported.has(saved) ? saved : 'zh'
  }

  let language = readLanguage()
  window.__WOODFLOOR_LANGUAGE__ = language

  const exact = new Map(Object.entries({
    '木地板 AI 选购顾问': 'Wood Flooring AI Consultant',
    '隐私与数据': 'Privacy and Data',
    '获取方案与后续联系': 'Get My Plan and Follow-Up',
    '您好，我是小木': 'Hello, I am Xiao Mu',
    '帮您更轻松地选到合适的木地板': 'Find the right flooring with greater confidence',
    '先选择您喜欢的导购风格，再告诉我房间、风格、预算和生活需求。': 'Choose a consultant style, then tell me about the room, design, budget and household needs.',
    '选择您喜欢的导购风格': 'Choose your consultant style',
    '点击人像即可选择并试听': 'Select a portrait to choose and preview the voice',
    '已选择': 'Selected',
    '选择并试听': 'Select and preview',
    '温暖亲和': 'Warm and friendly',
    '沉稳专业': 'Calm and professional',
    '年轻活力': 'Young and energetic',
    '成熟自信': 'Mature and confident',
    '语气柔和，适合耐心了解家庭需求。': 'A gentle style for patiently understanding household needs.',
    '表达稳重，适合讲解材质与性能差异。': 'A steady style for explaining materials and performance differences.',
    '节奏轻快，适合现代家居和年轻家庭。': 'An upbeat style for modern homes and younger households.',
    '讲解清晰，适合快速形成购买判断。': 'A clear, confident style for reaching a decision efficiently.',
    '云希': 'Yunxi',
    '云健': 'Yunjian',
    '云夏': 'Yunxia',
    '云扬': 'Yunyang',
    '小木': 'Xiao Mu',
    '正在检查本地选购记忆…': 'Checking local shopping memory…',
    '摄像头画面不会显示。只有您明确同意后，才会在本机保存人脸特征和选购摘要；默认不保存原始照片。': 'The camera view is not shown. Face features and the consultation summary are stored on this PC only after explicit consent; raw photos are not stored by default.',
    '重新开始': 'Start over',
    '更换导购': 'Change consultant',
    '随时为您服务': 'Ready to help',
    '正在持续听您说': 'Listening continuously',
    '正在整理建议': 'Preparing advice',
    '正在为您讲解': 'Speaking',
    '请再试一次': 'Please try again',
    '请继续说，全部讲完后点击“停止说话”。': 'Please continue. When finished, select “Stop speaking”.',
    '您可以直接说出需求，也可以输入文字。': 'You can speak your needs or type them.',
    '已确认的历史背景': 'Confirmed previous context',
    '正在为您整理合适的建议': 'Preparing suitable advice',
    '为您推荐': 'Recommended for you',
    '点击说话': 'Start speaking',
    '停止说话': 'Stop speaking',
    '产品对比': 'Compare products',
    '结束并总结': 'Finish and summarise',
    '本次咨询已完成': 'Consultation complete',
    '您的选购要点': 'Your flooring requirements',
    '铺装空间': 'Room',
    '偏好风格': 'Preferred style',
    '预算区间': 'Budget range',
    '特殊需求': 'Special requirements',
    '重点关注': 'Key priorities',
    '推荐产品': 'Recommended products',
    '尚未确认': 'Not confirmed',
    '暂无明确要求': 'No confirmed requirement',
    '需要继续了解需求': 'More information required',
    '下一步建议': 'Recommended next step',
    '本地选购记忆已保存': 'Local shopping memory saved',
    '下次继续本次方案': 'Continue this plan next time',
    '系统已在本机保存人脸特征和选购摘要，未保存原始照片。': 'Face features and the consultation summary are stored on this PC; raw photos are not stored.',
    '经您明确同意后，系统只在本机保存人脸特征和本次摘要，下次可继续咨询。': 'After explicit consent, face features and this summary are stored only on this PC so the consultation can continue next time.',
    '同意并保存本地记忆': 'Consent and save local memory',
    '继续咨询': 'Continue consultation',
    '开始新的咨询': 'Start a new consultation',
    '本地选购记忆': 'Local shopping memory',
    '欢迎回来': 'Welcome back',
    '我们可能找到了您之前同意保存的选购记录。': 'We may have found a shopping record that you previously agreed to save.',
    '确认前不会显示姓名或历史内容，避免误认造成信息泄露。': 'No name or history is shown before confirmation, which helps prevent disclosure after a mistaken match.',
    '没有完成确认': 'Confirmation was not completed',
    '重新识别': 'Recognise again',
    '正在重新识别…': 'Recognising again…',
    '正在准备新的咨询页面，请稍候…': 'Preparing the consultation page…',
    '继续上次咨询': 'Continue the previous consultation',
    '正在加载上次记录…': 'Loading the previous record…',
    '开始新的选购项目': 'Start a new flooring project',
    '正在创建新项目…': 'Creating a new project…',
    '这不是我': 'This is not me',
    '正在开始匿名咨询…': 'Starting an anonymous consultation…',
    '需要您的明确同意': 'Your explicit consent is required',
    '保存本地选购记忆': 'Save local shopping memory',
    '请正对屏幕并保持光线充足。系统会在本机保存数个人脸特征向量和本次选购摘要，不保存原始人脸照片。': 'Face the screen in good lighting. The system stores several face-feature vectors and this consultation summary on this PC, but does not store raw face photos.',
    '称呼（可选）': 'Preferred name (optional)',
    '我同意仅在本机保存人脸特征和本次选购记录，用于下次恢复咨询背景。': 'I consent to storing face features and this consultation record only on this PC so the context can be restored next time.',
    '同意并开始采集': 'Consent and start capture',
    '正在采集清晰人脸…': 'Capturing a clear face image…',
    '暂不保存': 'Do not save now',
    '最多选择两款': 'Select up to two',
    '请选择两款产品，即可查看完整参数对比。': 'Select two products to view a full comparison.',
    '推荐': 'Recommended',
    '已加入对比': 'Added to comparison',
    '加入对比': 'Add to comparison',
    '防水': 'Water resistant',
    '地暖': 'Underfloor heating',
    '宠物': 'Pet friendly',
    '支持': 'Supported',
    '需确认': 'Confirm with store',
    '我': 'Me',
    '发送': 'Send',
    '关闭提示': 'Close message',
    '关闭': 'Close',
    '关闭产品对比': 'Close product comparison',
    '例如：客厅用，家里有宠物，希望耐磨好清洁…': 'For example: living room, pets at home, durable and easy to clean…',
    '正在持续收音，请说完后点击“停止说话”…': 'Listening continuously. Select “Stop speaking” when finished…',
    '例如：王先生': 'For example: Alex',
    '客厅用，家里有宠物，希望耐磨又好清洁。': 'Living room, pets at home, with wear resistance and easy cleaning as priorities.',
    '卧室用，喜欢北欧原木风，想要脚感舒服。': 'Bedroom, Scandinavian natural-wood style, with comfortable underfoot feel.',
    '家里有地暖，应该选哪种地板？': 'We have underfloor heating. Which flooring should we choose?',
    '南方比较潮湿，想重点看看防水性能。': 'The home is humid, so water resistance is a priority.',
    '语音播放失败': 'Audio playback failed',
    '当前浏览器不支持语音识别，请使用 Chrome 或 Edge，也可以直接输入文字。': 'This browser does not support speech recognition. Use Chrome or Edge, or type your message.',
    '语音识别服务暂时不可用，请使用文字输入。': 'Speech recognition is temporarily unavailable. Please type your message.',
    '无法使用麦克风，请检查浏览器麦克风权限。': 'The microphone is unavailable. Check the browser microphone permission.',
    '还没有听到完整内容，请再次点击说话，讲完后再点击“停止说话”。': 'No complete message was captured. Start speaking again and select “Stop speaking” when finished.',
    '请先确认您同意仅在本机保存人脸特征和本次选购记录。': 'Please confirm that you consent to storing face features and this consultation record only on this PC.',
    '已加载经您确认的本地历史选购记忆。': 'Your confirmed local shopping memory has been loaded.',
    '正在本机检查是否存在您之前同意保存的选购记录…': 'Checking this PC for a shopping record you previously agreed to save…',
    '正在重新检查本地选购记忆…': 'Checking local shopping memory again…',
    '本次人脸确认已经超时。请点击“重新识别”，或选择“这不是我”开始新的匿名咨询。': 'This face-confirmation attempt has expired. Select “Recognise again”, or choose “This is not me” to start anonymously.',
    '暂时无法连接后端服务。请确认 Backend 正在运行，然后重试。': 'The backend service is unavailable. Confirm that it is running, then try again.',
    '查看并删除我的本地数据': 'View and delete my local data',
    '数据和后续服务': 'Data and follow-up services'
  }))

  const productNames = new Map(Object.entries({
    '云杉浅灰 SPC 锁扣地板': 'Light Grey Spruce SPC Click Flooring',
    '原木橡木多层实木地板': 'Natural Oak Engineered Wood Flooring',
    '晨雾灰强化复合地板': 'Morning Mist Grey Laminate Flooring',
    '深胡桃防水 SPC 地板': 'Dark Walnut Waterproof SPC Flooring',
    '温润浅橡三层实木地板': 'Warm Light Oak Three-Layer Wood Flooring',
    '奶油白高耐磨强化地板': 'Cream White High-Wear Laminate Flooring'
  }))

  function translateText(input) {
    if (language !== 'en' || typeof input !== 'string') return input
    const leading = input.match(/^\s*/)?.[0] || ''
    const trailing = input.match(/\s*$/)?.[0] || ''
    let text = input.trim()
    if (!text) return input
    if (exact.has(text)) return leading + exact.get(text) + trailing

    for (const [zh, en] of productNames.entries()) text = text.replaceAll(zh, en)
    text = text
      .replaceAll('云希', 'Yunxi')
      .replaceAll('云健', 'Yunjian')
      .replaceAll('云夏', 'Yunxia')
      .replaceAll('云扬', 'Yunyang')
      .replaceAll('小木', 'Xiao Mu')

    let match = text.match(/^您好，我是 Xiao Mu · (.+)$/)
    if (match) return `${leading}Hello, I am Xiao Mu · ${match[1]}${trailing}`
    match = text.match(/^和(.+)开始咨询$/)
    if (match) return `${leading}Start consultation with ${match[1]}${trailing}`
    match = text.match(/^Xiao Mu · (.+)$/)
    if (match) return `${leading}Xiao Mu · ${match[1]}${trailing}`
    match = text.match(/^持续收音中：“(.+)”$/)
    if (match) return `${leading}Listening: “${match[1]}”${trailing}`
    match = text.match(/^刚刚听到：“(.+)”$/)
    if (match) return `${leading}Heard: “${match[1]}”${trailing}`

    text = text
      .replaceAll(' · 已确认回访记忆', ' · confirmed returning-customer memory')
      .replaceAll('正在为您整理合适的建议', 'Preparing suitable advice')

    return leading + text + trailing
  }

  function translateElement(element) {
    if (language !== 'en' || !(element instanceof Element)) return
    for (const attribute of ['placeholder', 'aria-label', 'title', 'value']) {
      const value = element.getAttribute(attribute)
      if (value) element.setAttribute(attribute, translateText(value))
    }
  }

  function translateTree(root) {
    if (language !== 'en') return
    if (root.nodeType === Node.TEXT_NODE) {
      const translated = translateText(root.nodeValue || '')
      if (translated !== root.nodeValue) root.nodeValue = translated
      return
    }
    if (!(root instanceof Element) && root !== document) return
    if (root instanceof Element) translateElement(root)
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT)
    let node = walker.nextNode()
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        const translated = translateText(node.nodeValue || '')
        if (translated !== node.nodeValue) node.nodeValue = translated
      } else if (node instanceof Element) {
        translateElement(node)
      }
      node = walker.nextNode()
    }
  }

  function applyDocumentLanguage() {
    document.documentElement.lang = language === 'en' ? 'en-AU' : 'zh-CN'
    document.documentElement.dataset.uiLanguage = language
    document.title = language === 'en' ? 'Wood Flooring AI Consultant' : '木地板 AI 选购顾问'
  }

  function installSpeechSynthesisLanguageGuard() {
    if (!window.speechSynthesis || window.__WOODFLOOR_SPEECH_GUARD__) return
    const originalSpeak = window.speechSynthesis.speak.bind(window.speechSynthesis)
    window.speechSynthesis.speak = (utterance) => {
      utterance.lang = language === 'en' ? 'en-US' : 'zh-CN'
      originalSpeak(utterance)
    }
    window.__WOODFLOOR_SPEECH_GUARD__ = true
  }

  function createToggle() {
    if (document.getElementById('woodfloor-language-toggle')) return
    const button = document.createElement('button')
    button.id = 'woodfloor-language-toggle'
    button.type = 'button'
    button.textContent = language === 'en' ? '中文' : 'EN'
    button.setAttribute('aria-label', language === 'en' ? 'Switch to Chinese' : '切换为英文')
    Object.assign(button.style, {
      position: 'fixed',
      zIndex: '3000',
      top: '16px',
      right: '18px',
      minWidth: '58px',
      height: '40px',
      padding: '0 14px',
      border: '1px solid rgba(112,76,55,.24)',
      borderRadius: '999px',
      background: 'rgba(255,253,249,.96)',
      boxShadow: '0 8px 24px rgba(71,47,34,.15)',
      color: '#6f4632',
      font: '700 14px Inter, system-ui, sans-serif',
      cursor: 'pointer',
      backdropFilter: 'blur(10px)'
    })
    button.addEventListener('click', () => {
      const next = language === 'en' ? 'zh' : 'en'
      window.localStorage.setItem(STORAGE_KEY, next)
      window.dispatchEvent(new CustomEvent(LANGUAGE_EVENT, { detail: { language: next } }))
      window.location.reload()
    })
    document.body.appendChild(button)
  }

  applyDocumentLanguage()
  installSpeechSynthesisLanguageGuard()

  window.addEventListener('DOMContentLoaded', () => {
    createToggle()
    translateTree(document.body)
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === 'characterData') translateTree(record.target)
        for (const node of record.addedNodes) translateTree(node)
      }
    })
    observer.observe(document.body, { subtree: true, childList: true, characterData: true })
  })
})()
