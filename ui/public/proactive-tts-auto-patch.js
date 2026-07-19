(() => {
  const previousFetch = window.fetch.bind(window)

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

  function isCurrentProactiveNarration(body) {
    if (!body || body.provider !== 'local' || typeof body.text !== 'string') return false
    const dock = document.getElementById('proactive-sales-dock')
    const visibleText = dock?.querySelector('.proactive-sales-text')?.textContent?.trim() || ''
    return Boolean(
      dock &&
      !dock.hidden &&
      dock.classList.contains('visible') &&
      visibleText &&
      visibleText === body.text.trim(),
    )
  }

  window.fetch = (input, init) => {
    const url = requestUrl(input)
    const body = readJsonBody(init)
    if (!url.includes('/api/tts') || !isCurrentProactiveNarration(body)) {
      return previousFetch(input, init)
    }

    const headers = new Headers(init?.headers)
    headers.set('Content-Type', 'application/json; charset=utf-8')
    headers.set('X-Woodfloor-TTS-Caller', 'proactive-narration')
    return previousFetch(input, {
      ...init,
      headers,
      body: JSON.stringify({ ...body, provider: 'auto' }),
    })
  }
})()
