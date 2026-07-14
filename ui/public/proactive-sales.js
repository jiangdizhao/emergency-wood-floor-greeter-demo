(() => {
  const previousFetch = window.fetch.bind(window)
  const IDLE_DELAYS_MS = [8000, 10000, 10000, 14000]
  const MAX_PROACTIVE_STEPS = IDLE_DELAYS_MS.length
  const enabledKey = 'woodfloor_proactive_sales_enabled'
  const sessionKey = 'woodfloor_active_session_id'

  let enabled = localStorage.getItem(enabledKey) !== '0'
  let step = 0
  let timer = null
  let generation = 0
  let currentAudio = null
  let latestProducts = []
  let latestRecommended = []
  let latestProfile = null
  let latestPromotions = []
  let latestVoice = 'zm_yunxi'
  let latestTtsUrl = 'http://127.0.0.1:8000/api/tts'
  let latestLanguage = language()
  let observer = null

  const promotionEnglish = {
    'DEMO-SPC-60': {
      title: 'Whole-Home SPC Support Package — Demo Promotion',
      summary:
        'Selected SPC products with a suggested area of at least 60 square metres may be assessed for store installation-support benefits. The exact benefit and final quotation require written store confirmation.',
    },
    'DEMO-WOOD-CONSULT': {
      title: 'Natural Wood Consultation Benefit — Demo Promotion',
      summary:
        'The natural-wood collection has a demo consultation benefit covering samples, room coordination and installation-condition discussion. It does not promise free installation or a fixed discount.',
    },
    'DEMO-VALUE-ROOM': {
      title: 'Room Renovation Value Package — Demo Promotion',
      summary:
        'Selected laminate products may be assessed as a room-renovation demo package. Damp areas or projects requiring strong water resistance still need a separate material review.',
    },
  }

  const productEnglish = {
    'WF-SPC-001': {
      name: 'Light Grey Spruce SPC Click Flooring',
      type: 'SPC',
      color: 'light grey',
      selling_points: ['strong water resistance', 'high wear resistance'],
    },
    'WF-WOOD-002': {
      name: 'Natural Oak Engineered Wood Flooring',
      type: 'engineered wood',
      color: 'natural oak',
      selling_points: ['natural underfoot feel', 'authentic wood grain'],
    },
    'WF-LAM-003': {
      name: 'Morning Mist Grey Laminate Flooring',
      type: 'laminate',
      color: 'grey tone',
      selling_points: ['strong value for money', 'good wear resistance'],
    },
    'WF-SPC-004': {
      name: 'Dark Walnut Waterproof SPC Flooring',
      type: 'SPC',
      color: 'dark walnut',
      selling_points: ['rich dark-walnut appearance', 'strong water and wear resistance'],
    },
    'WF-WOOD-005': {
      name: 'Warm Light Oak Three-Layer Wood Flooring',
      type: 'three-layer wood',
      color: 'light oak',
      selling_points: ['comfortable underfoot feel', 'authentic natural wood texture'],
    },
    'WF-LAM-006': {
      name: 'Cream White High-Wear Laminate Flooring',
      type: 'laminate',
      color: 'cream white',
      selling_points: ['bright cream-white appearance', 'wear-resistant and easy to maintain'],
    },
  }

  function language() {
    const configured = window.__WOODFLOOR_LANGUAGE__
    const stored = localStorage.getItem('woodfloor_ui_language')
    return configured === 'en' || stored === 'en' ? 'en' : 'zh'
  }

  function containsChinese(value) {
    return typeof value === 'string' && /[\u3400-\u4dbf\u4e00-\u9fff]/.test(value)
  }

  function requestUrl(input) {
    if (typeof input === 'string') return input
    if (input instanceof URL) return input.href
    return input && typeof input.url === 'string' ? input.url : ''
  }

  function readJsonBody(init) {
    try {
      return init && typeof init.body === 'string' ? JSON.parse(init.body) : null
    } catch {
      return null
    }
  }

  function stopAudio() {
    if (!currentAudio) return
    currentAudio.pause()
    currentAudio.src = ''
    currentAudio = null
  }

  function clearTimer() {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  function isConversationVisible() {
    return Boolean(document.querySelector('.consultation-screen'))
  }

  function isInteractionBusy() {
    if (!isConversationVisible()) return true
    if (document.querySelector('.thinking-bubble')) return true
    if (document.querySelector('.status-pulse.listening, .status-pulse.processing, .status-pulse.speaking')) return true
    if (document.querySelector('.modal-backdrop')) return true
    const textarea = document.querySelector('.conversation-card textarea')
    if (textarea && textarea.value.trim()) return true
    return Boolean(currentAudio)
  }

  function schedule(delayOverride) {
    clearTimer()
    if (!enabled || step >= MAX_PROACTIVE_STEPS || !isConversationVisible()) return
    const token = ++generation
    const delay = delayOverride ?? IDLE_DELAYS_MS[Math.min(step, IDLE_DELAYS_MS.length - 1)]
    timer = window.setTimeout(() => {
      timer = null
      if (token !== generation || !enabled || !isConversationVisible()) return
      if (isInteractionBusy()) {
        schedule(1800)
        return
      }
      void deliverStep()
    }, delay)
  }

  function resetCadence({ stopSpeech = true } = {}) {
    generation += 1
    clearTimer()
    step = 0
    if (stopSpeech) stopAudio()
    if (enabled && isConversationVisible()) schedule()
  }

  function productById(id) {
    return latestProducts.find((item) => item && item.id === id) || null
  }

  function selectedProducts() {
    const output = []
    const seen = new Set()
    for (const item of latestRecommended) {
      if (!item || seen.has(item.id)) continue
      output.push(item)
      seen.add(item.id)
    }
    for (const id of latestProfile?.recommended_product_ids || []) {
      const item = productById(id)
      if (!item || seen.has(item.id)) continue
      output.push(item)
      seen.add(item.id)
    }
    for (const item of latestProducts) {
      if (!item || seen.has(item.id)) continue
      output.push(item)
      seen.add(item.id)
    }
    return output
  }

  function englishProduct(product) {
    const mapped = productEnglish[product?.id]
    if (mapped) return mapped
    return {
      name: `Flooring option ${product?.id || ''}`.trim(),
      type: 'flooring',
      color: 'a coordinated colour direction',
      selling_points: ['a practical balance of performance and maintenance', 'a useful comparison point'],
    }
  }

  function productStory(product, alternate = false) {
    const lang = language()
    if (lang === 'en') {
      const localized = englishProduct(product)
      const pointText = localized.selling_points.slice(0, 2).join(' and ')
      return alternate
        ? `While you take your time, here is another useful direction. ${localized.name} is a ${localized.type} option in ${localized.color}; ${pointText}. It is worth keeping as a contrast rather than deciding from one material alone.`
        : `You can take your time. One representative option is ${localized.name}. Its useful strengths are ${pointText}, so it gives you a concrete reference before we narrow the project details.`
    }

    const points = Array.isArray(product?.selling_points) ? product.selling_points.filter(Boolean).slice(0, 2) : []
    const pointText = points.join('、')
    return alternate
      ? `您可以慢慢看，我再补充一个不同方向。${product.name}属于${product.type}路线，颜色是${product.color}，特点是${pointText || '在外观、维护和预算之间提供另一种平衡'}。先把它作为对照保留下来，比只看一种材料更容易判断取舍。`
      : `您可以先慢慢感受。我先补充一款有代表性的产品，${product.name}的主要特点是${pointText || '兼顾性能、外观与日常维护'}。先有一个具体产品作参照，后面再收窄空间、预算或颜色会更轻松。`
  }

  function collectionStory() {
    const driver = latestProfile?.primary_purchase_driver || Object.keys(latestProfile?.priorities || {})[0] || ''
    if (language() === 'en') {
      if (String(driver).toLowerCase().includes('wear') || String(driver).includes('耐磨')) {
        return 'For a wear-resistance-first project, the store does not look at the rating alone. The durable easy-care family route also considers cleaning frequency, pets or children, water exposure and the real traffic level of the room, so the recommendation is based on how the home is actually used.'
      }
      return 'Our store works with four practical routes: durable easy-care family flooring, underfloor-heating-ready options, natural wood comfort and value-focused renovation. The point is not to push every feature at once, but to show which benefit is worth keeping and what trade-off comes with it.'
    }
    if (String(driver).includes('耐磨')) {
      return '对于耐磨优先的家庭，我们不会只报一个耐磨等级。耐磨易维护路线还会一起考虑清洁频率、宠物或孩子、偶发水渍以及房间真实的人流强度，这样选出来的产品才更贴近日常使用。'
    }
    return '门店的四条核心路线分别是耐磨易维护、地暖适配、高品质实木质感和经济实用。高级选购不是把所有优点都堆在一起，而是帮您看清哪项价值值得保留，以及它对应的材料取舍。'
  }

  function promotionStory() {
    const promotion = latestPromotions[0]
    if (!promotion) return collectionStory()
    if (language() === 'en') {
      const mapped = promotionEnglish[promotion.promotion_id]
      const title = mapped?.title || 'Current Demo Promotion'
      const summary = mapped?.summary || 'A demo promotion is currently listed, with exact eligibility and benefits subject to written store confirmation.'
      return `${title}. ${summary} I am mentioning it as useful background only, not as a promise of a discount or final entitlement.`
    }
    const title = promotion.title || '当前演示活动'
    const summary = promotion.approved_message || promotion.summary || '门店当前列有一项演示活动，具体适用条件和权益需要由门店书面确认。'
    return `${title}。${summary}我先把它作为选购背景告诉您，不把它说成已经确定的折扣或最终权益。`
  }

  function contactStory() {
    const eligible = latestProfile?.contact_prompt_eligible === true && latestProfile?.contact_opt_in !== true
    if (!eligible) {
      return language() === 'en'
        ? 'There is no need to decide immediately. You can compare the product directions on screen, and whenever one detail becomes clear, I will continue from that point instead of restarting the consultation.'
        : '现在不需要马上做决定。您可以先看看屏幕上的产品对比，等某个细节想清楚后再继续，我会从当前进度接着讲，不会重新开始盘问。'
    }
    return language() === 'en'
      ? 'If it would be useful, the “Get My Plan and Follow-Up” form can save a contact method locally so the store can send this comparison and follow up on samples or quotation. This is optional, and marketing updates require a separate choice.'
      : '如果您觉得这份对比有价值，可以点击“获取方案与后续联系”，自愿在本机留下联系方式，用于接收本次方案、样板或报价跟进。新品和优惠推送是独立授权，不会默认勾选。'
  }

  function messageForStep(index) {
    const products = selectedProducts()
    if (index === 0 && products[0]) return { text: productStory(products[0], false), offerContact: false }
    if (index === 1 && products[1]) return { text: productStory(products[1], true), offerContact: false }
    if (index === 2) return { text: promotionStory(), offerContact: false }
    return {
      text: contactStory(),
      offerContact: latestProfile?.contact_prompt_eligible === true && latestProfile?.contact_opt_in !== true,
    }
  }

  function ensureDock() {
    let dock = document.getElementById('proactive-sales-dock')
    if (dock) return dock
    dock = document.createElement('aside')
    dock.id = 'proactive-sales-dock'
    dock.className = 'proactive-sales-dock'
    dock.hidden = true
    dock.innerHTML = `
      <div class="proactive-sales-heading">
        <span class="proactive-sales-pulse" aria-hidden="true"></span>
        <strong></strong>
        <button type="button" class="proactive-sales-toggle"></button>
      </div>
      <p class="proactive-sales-text"></p>
      <a class="proactive-sales-contact" hidden></a>
    `
    document.body.appendChild(dock)
    dock.querySelector('.proactive-sales-toggle').addEventListener('click', () => {
      enabled = !enabled
      localStorage.setItem(enabledKey, enabled ? '1' : '0')
      updateDockLabels()
      if (enabled) resetCadence({ stopSpeech: false })
      else {
        generation += 1
        clearTimer()
        stopAudio()
      }
    })
    return dock
  }

  function updateDockLabels() {
    const dock = ensureDock()
    const lang = language()
    latestLanguage = lang
    dock.querySelector('.proactive-sales-heading strong').textContent =
      lang === 'en' ? 'Xiao Mu · proactive guide' : '小木 · 主动讲解'
    dock.querySelector('.proactive-sales-toggle').textContent = enabled
      ? lang === 'en'
        ? 'Pause'
        : '暂停'
      : lang === 'en'
        ? 'Resume'
        : '继续'
    const contact = dock.querySelector('.proactive-sales-contact')
    contact.textContent = lang === 'en' ? 'Get My Plan and Follow-Up' : '获取方案与后续联系'
    const sessionId = sessionStorage.getItem(sessionKey) || latestProfile?.session_id || ''
    contact.href = `/follow-up.html${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''}`
  }

  function showMessage(text, offerContact) {
    const dock = ensureDock()
    updateDockLabels()
    dock.hidden = false
    dock.classList.add('visible')
    dock.querySelector('.proactive-sales-text').textContent = text
    const contact = dock.querySelector('.proactive-sales-contact')
    contact.hidden = !offerContact
  }

  async function speak(text) {
    stopAudio()
    const lang = language()
    const voice = lang === 'en'
      ? ({ zm_yunxi: 'am_liam', zm_yunjian: 'am_michael', zm_yunxia: 'am_puck', zm_yunyang: 'am_onyx' }[latestVoice] || latestVoice || 'am_liam')
      : latestVoice.startsWith('am_')
        ? 'zm_yunxi'
        : latestVoice || 'zm_yunxi'
    const speechText = lang === 'en' && containsChinese(text)
      ? 'Let me continue with the selected flooring options and explain the practical differences.'
      : text
    try {
      const response = await previousFetch(latestTtsUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ text: speechText, language: lang, provider: 'local', voice }),
      })
      if (!response.ok) throw new Error(`TTS ${response.status}`)
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      currentAudio = audio
      await new Promise((resolve) => {
        audio.onended = resolve
        audio.onerror = resolve
        audio.play().catch(resolve)
      })
      if (currentAudio === audio) currentAudio = null
      URL.revokeObjectURL(url)
    } catch (error) {
      currentAudio = null
      console.warn('Proactive sales narration could not play:', error)
    }
  }

  async function deliverStep() {
    const currentStep = step
    const message = messageForStep(currentStep)
    if (!message?.text) {
      step += 1
      schedule()
      return
    }
    showMessage(message.text, message.offerContact)
    step += 1
    await speak(message.text)
    if (enabled && step < MAX_PROACTIVE_STEPS) schedule()
  }

  function capturePayload(url, payload) {
    if (!payload || typeof payload !== 'object') return
    if (url.includes('/api/products') && Array.isArray(payload.products)) latestProducts = payload.products
    if (Array.isArray(payload.recommended_products)) latestRecommended = payload.recommended_products
    if (payload.customer_profile && typeof payload.customer_profile === 'object') latestProfile = payload.customer_profile
    if (Array.isArray(payload.active_promotions)) latestPromotions = payload.active_promotions
    if (typeof payload.session_id === 'string') sessionStorage.setItem(sessionKey, payload.session_id)
    if (typeof payload.customer_profile?.session_id === 'string') {
      sessionStorage.setItem(sessionKey, payload.customer_profile.session_id)
    }
  }

  window.fetch = async (input, init) => {
    const url = requestUrl(input)
    const body = readJsonBody(init)
    if (url.includes('/api/tts')) {
      latestTtsUrl = url
      if (typeof body?.voice === 'string' && body.voice) latestVoice = body.voice
      if (body?.language === 'en' || body?.language === 'zh') latestLanguage = body.language
    }
    if (url.includes('/api/chat') && body?.text) resetCadence()

    const response = await previousFetch(input, init)
    try {
      const contentType = response.headers.get('content-type') || ''
      if (contentType.includes('application/json')) {
        const payload = await response.clone().json()
        capturePayload(url, payload)
        if (url.includes('/api/chat') || url.includes('/api/identity/session/')) {
          resetCadence({ stopSpeech: false })
        }
      }
    } catch {
      // Proactive narration must never alter the real API response.
    }
    return response
  }

  function installActivityListeners() {
    const resetFromUser = (event) => {
      if (!event.isTrusted) return
      if (!isConversationVisible()) return
      const target = event.target
      if (target instanceof Element && target.closest('#proactive-sales-dock')) return
      resetCadence()
    }
    document.addEventListener('pointerdown', resetFromUser, true)
    document.addEventListener('keydown', resetFromUser, true)
    document.addEventListener('input', resetFromUser, true)
  }

  function observeScreens() {
    observer = new MutationObserver(() => {
      const dock = ensureDock()
      if (!isConversationVisible()) {
        dock.hidden = true
        clearTimer()
        stopAudio()
        return
      }
      updateDockLabels()
      if (enabled && timer === null && currentAudio === null && step < MAX_PROACTIVE_STEPS) schedule()
    })
    observer.observe(document.getElementById('root') || document.body, { childList: true, subtree: true })
  }

  async function loadPromotionCatalog() {
    try {
      const response = await previousFetch('http://127.0.0.1:8000/api/promotions/active')
      if (!response.ok) return
      const payload = await response.json()
      if (Array.isArray(payload.promotions)) latestPromotions = payload.promotions
    } catch {
      // Promotions are optional. Product and collection stories still work offline.
    }
  }

  window.addEventListener('DOMContentLoaded', () => {
    ensureDock()
    updateDockLabels()
    installActivityListeners()
    observeScreens()
    void loadPromotionCatalog()
  })

  window.addEventListener('beforeunload', () => {
    clearTimer()
    stopAudio()
    observer?.disconnect()
  })
})()
