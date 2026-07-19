import {
  prewarmRealtimeRecognition,
  realtimeAsrSelected,
  resetRealtimeRecognition,
} from './realtimeSpeechRecognition'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? 'http://127.0.0.1:8000'
const PROVIDER_STORAGE_KEY = 'woodfloor_asr_provider'
const BROWSER_PROVIDER = 'browser'
const REALTIME_PROVIDER = 'gpt-realtime-2'
const CONTROL_ID = 'woodfloor-asr-mode-control'
const STYLE_ID = 'woodfloor-asr-mode-control-style'

type RealtimeStatus = {
  configured?: boolean
  enabled?: boolean
  model?: string
}

function selectedProvider(): string {
  return realtimeAsrSelected() ? REALTIME_PROVIDER : BROWSER_PROVIDER
}

function setProvider(provider: string): void {
  window.localStorage.setItem(PROVIDER_STORAGE_KEY, provider)
  resetRealtimeRecognition()
  window.dispatchEvent(
    new CustomEvent('woodfloor:asr-provider-changed', {
      detail: { provider },
    }),
  )
}

function installStyle(): void {
  if (document.getElementById(STYLE_ID)) return
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = `
    #${CONTROL_ID} {
      position: fixed;
      right: 18px;
      bottom: 18px;
      z-index: 1200;
      display: flex;
      align-items: center;
      gap: 8px;
      max-width: min(440px, calc(100vw - 36px));
      padding: 9px 11px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      border-radius: 14px;
      background: rgba(20, 25, 31, 0.94);
      color: #f4f4f2;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.32);
      backdrop-filter: blur(12px);
      font: 500 12px/1.25 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    #${CONTROL_ID} label {
      white-space: nowrap;
      color: rgba(255, 255, 255, 0.74);
    }
    #${CONTROL_ID} select {
      min-width: 190px;
      padding: 6px 30px 6px 9px;
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 9px;
      background: #202831;
      color: #fff;
      font: inherit;
    }
    #${CONTROL_ID} .asr-mode-state {
      overflow: hidden;
      max-width: 145px;
      color: #9dd9b7;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    #${CONTROL_ID}[data-error="true"] .asr-mode-state {
      color: #ffbf9e;
    }
    @media (max-width: 760px) {
      #${CONTROL_ID} {
        right: 10px;
        bottom: 10px;
        left: 10px;
        justify-content: space-between;
      }
      #${CONTROL_ID} select {
        min-width: 0;
        flex: 1;
      }
      #${CONTROL_ID} .asr-mode-state {
        display: none;
      }
    }
  `
  document.head.appendChild(style)
}

async function fetchStatus(): Promise<RealtimeStatus> {
  const response = await fetch(`${API_BASE_URL}/api/realtime/status`, {
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
  return (await response.json()) as RealtimeStatus
}

function isListening(): boolean {
  return Boolean(document.querySelector('.status-pulse.listening'))
}

function removeControl(): void {
  document.getElementById(CONTROL_ID)?.remove()
}

function createControl(): HTMLElement {
  const control = document.createElement('div')
  control.id = CONTROL_ID
  control.setAttribute('role', 'group')
  control.setAttribute('aria-label', '语音识别模式')

  const label = document.createElement('label')
  label.htmlFor = `${CONTROL_ID}-select`
  label.textContent = '语音识别'

  const select = document.createElement('select')
  select.id = `${CONTROL_ID}-select`
  select.setAttribute('aria-label', '选择语音识别模式')

  const browserOption = document.createElement('option')
  browserOption.value = BROWSER_PROVIDER
  browserOption.textContent = '浏览器识别（兼容模式）'

  const realtimeOption = document.createElement('option')
  realtimeOption.value = REALTIME_PROVIDER
  realtimeOption.textContent = 'GPT Realtime 2.1（默认）'
  realtimeOption.disabled = true

  select.append(browserOption, realtimeOption)
  select.value = selectedProvider()

  const state = document.createElement('span')
  state.className = 'asr-mode-state'
  state.textContent = '正在检查 Realtime…'

  select.addEventListener('change', () => {
    const provider = select.value
    setProvider(provider)
    if (provider === REALTIME_PROVIDER) {
      state.textContent = '正在预连接…'
      control.dataset.error = 'false'
      void prewarmRealtimeRecognition()
        .then(() => {
          state.textContent = 'Realtime 已就绪'
        })
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : String(error)
          state.textContent = '连接失败，已切回兼容模式'
          control.dataset.error = 'true'
          console.warn('GPT Realtime prewarm failed:', message)
          setProvider(BROWSER_PROVIDER)
          select.value = BROWSER_PROVIDER
        })
    } else {
      state.textContent = '使用浏览器兼容识别'
      control.dataset.error = 'false'
    }
  })

  control.append(label, select, state)

  void fetchStatus()
    .then((status) => {
      const configured = Boolean(status.configured && status.enabled)
      realtimeOption.disabled = !configured
      realtimeOption.textContent = configured
        ? `GPT Realtime ${status.model ?? '2.1'}（默认）`
        : 'GPT Realtime（Backend 未配置）'

      if (!configured && select.value === REALTIME_PROVIDER) {
        setProvider(BROWSER_PROVIDER)
        select.value = BROWSER_PROVIDER
      }

      if (select.value === REALTIME_PROVIDER && configured) {
        state.textContent = '正在预连接…'
        return prewarmRealtimeRecognition().then(() => {
          state.textContent = 'Realtime 已就绪'
        })
      }

      state.textContent = configured ? '可切换 Realtime' : '请先配置 OPENAI_API_KEY'
      return undefined
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error)
      realtimeOption.disabled = true
      state.textContent = 'Realtime 状态不可用'
      control.dataset.error = 'true'
      console.warn('Could not load GPT Realtime status:', message)
      if (select.value === REALTIME_PROVIDER) {
        setProvider(BROWSER_PROVIDER)
        select.value = BROWSER_PROVIDER
      }
    })

  select.disabled = isListening()
  return control
}

function syncControl(): void {
  const inConversation = Boolean(document.querySelector('.consultation-screen'))
  const existing = document.getElementById(CONTROL_ID)
  if (!inConversation) {
    if (existing) removeControl()
    return
  }
  if (!existing) {
    document.body.appendChild(createControl())
    return
  }
  const select = existing.querySelector<HTMLSelectElement>('select')
  if (select) select.disabled = isListening()
}

function showAutomaticFallback(event: Event): void {
  const detail = (event as CustomEvent<{ reason?: string }>).detail
  const control = document.getElementById(CONTROL_ID)
  const select = control?.querySelector<HTMLSelectElement>('select')
  const state = control?.querySelector<HTMLElement>('.asr-mode-state')
  if (select) select.value = BROWSER_PROVIDER
  if (state) state.textContent = 'Realtime 故障，已切换浏览器识别'
  if (control) control.dataset.error = 'true'
  console.warn('GPT Realtime input failed; Browser ASR is now active:', detail?.reason ?? 'unknown error')
}

function installAsrModeControl(): void {
  installStyle()
  syncControl()
  window.addEventListener('woodfloor:asr-provider-fallback', showAutomaticFallback)
  const observer = new MutationObserver(syncControl)
  observer.observe(document.getElementById('root') ?? document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['class'],
  })
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', installAsrModeControl, { once: true })
} else {
  installAsrModeControl()
}
