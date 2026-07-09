import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import {
  API_BASE_URL,
  compareProducts,
  getProducts,
  getSessionStatus,
  getVisionStatus,
  resetSession,
  sendChat,
  sendDemoEvent,
  sendVoiceGreeting,
  startVision,
  stopVision,
  streamUrl,
  type CompareRow,
  type CustomerProfile,
  type FlooringProduct,
  type SessionState,
  type VisionStatus,
} from './api'

type ChatMessage = {
  id: string
  role: 'agent' | 'customer' | 'system'
  text: string
}

const WELCOME_MESSAGE =
  '你好，欢迎来到木地板体验区。我可以帮你了解不同木地板的材质、颜色、耐磨、防水和地暖适配情况。你可以直接问我，比如家里有宠物怎么选，或者哪种适合地暖。'

const DEMO_PROMPTS = [
  '家里有宠物，客厅用，现代简约，预算中等，哪种地板好打理？',
  '如果家里装了地暖，应该选 SPC、强化地板还是实木？',
  '预算有限但想要耐磨一点，适合推荐哪款？',
  '我喜欢北欧原木风，卧室用，脚感舒服一点怎么选？',
  '潮湿环境或者回南天比较严重，哪种地板更合适？',
  'SPC 地板和多层实木地板有什么区别？',
]

const INITIAL_PROFILE: CustomerProfile = {
  session_id: 'demo-session-001',
  customer_name: null,
  phone: null,
  room_type: null,
  style: null,
  budget: null,
  special_needs: [],
  concerns: [],
  recommended_product_ids: [],
  conversation_summary: '',
  follow_up_status: '未建档',
  follow_up_suggestion: '',
}

const INITIAL_VISION_STATUS: VisionStatus = {
  ok: true,
  running: false,
  camera_opened: false,
  person_detected: false,
  distance: 'NONE',
  face_height_ratio: 0,
  face_area_ratio: 0,
  face_close_votes: 0,
  face_window_size: 0,
  stable_close: false,
  wave_detected: false,
  raw_wave_event: null,
  raw_wave_ignored_reason: null,
  greeting_recent: false,
  last_wave_event: null,
  last_wave_at: null,
  state: 'IDLE',
  error: null,
  fps_estimate: 0,
  wave_debug: {},
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function stateLabel(state: SessionState): string {
  const labels: Record<SessionState, string> = {
    IDLE: '待机',
    PERSON_DETECTED_FAR: '检测到顾客，但距离较远',
    PERSON_CLOSE_WAITING_GREETING: '顾客已靠近，等待问候',
    GREETING_RECEIVED: '已收到近距离问候',
    INTRODUCING_PRODUCTS: '正在介绍产品',
    CONVERSATION_ACTIVE: '自由对话中',
    SESSION_END: '会话结束',
  }
  return labels[state] ?? state
}

function yesNo(value: boolean): string {
  return value ? '是' : '否'
}

function nextPromptIndex(current: number): number {
  return (current + 1) % DEMO_PROMPTS.length
}

function App() {
  const [visionStatus, setVisionStatus] = useState<VisionStatus>(INITIAL_VISION_STATUS)
  const [products, setProducts] = useState<FlooringProduct[]>([])
  const [recommendedProducts, setRecommendedProducts] = useState<FlooringProduct[]>([])
  const [profile, setProfile] = useState<CustomerProfile>(INITIAL_PROFILE)
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'm-welcome',
      role: 'agent',
      text: '请靠近屏幕，并向我挥手或点击模拟问候按钮。我会开始介绍木地板产品。',
    },
  ])
  const [promptIndex, setPromptIndex] = useState(0)
  const [inputText, setInputText] = useState(DEMO_PROMPTS[0])
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [compareRows, setCompareRows] = useState<CompareRow[]>([])
  const [streamSrc, setStreamSrc] = useState(streamUrl())
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const handledGreetingRef = useRef<number | null>(null)

  const recommendedIds = useMemo(
    () => new Set(recommendedProducts.map((product) => product.id)),
    [recommendedProducts],
  )

  useEffect(() => {
    void refreshCatalogAndSession()
  }, [])

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const status = await getVisionStatus()
        if (alive) {
          setVisionStatus(status)
          setError(null)
        }
      } catch (err) {
        if (alive) {
          setError(err instanceof Error ? err.message : String(err))
        }
      }
    }

    void poll()
    const timer = window.setInterval(poll, 700)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    const lastWaveAt = visionStatus.last_wave_at
    if (visionStatus.state !== 'GREETING_RECEIVED' || lastWaveAt === null) {
      return
    }
    if (!visionStatus.stable_close || visionStatus.distance !== 'CLOSE') {
      return
    }
    if (handledGreetingRef.current === lastWaveAt) {
      return
    }

    handledGreetingRef.current = lastWaveAt
    appendMessage('system', `视觉检测到近距离挥手问候：${visionStatus.last_wave_event ?? 'WAVE'}`)
    appendMessage('agent', WELCOME_MESSAGE)

    const timer = window.setTimeout(() => {
      void runAction('intro_finished', async () => {
        await sendDemoEvent('intro_finished')
        const session = await getSessionStatus()
        setProfile(session.customer_profile)
      })
    }, 800)

    return () => window.clearTimeout(timer)
  }, [visionStatus.distance, visionStatus.last_wave_at, visionStatus.last_wave_event, visionStatus.stable_close, visionStatus.state])

  async function refreshCatalogAndSession() {
    await runAction('refresh', async () => {
      const [catalog, session] = await Promise.all([getProducts(), getSessionStatus()])
      setProducts(catalog.products)
      setProfile(session.customer_profile)
      const ids = new Set(session.customer_profile.recommended_product_ids)
      setRecommendedProducts(catalog.products.filter((product) => ids.has(product.id)))
    })
  }

  function appendMessage(role: ChatMessage['role'], text: string) {
    setMessages((current) => [
      ...current,
      {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        role,
        text,
      },
    ])
  }

  function advanceSuggestedPrompt() {
    setPromptIndex((current) => {
      const next = nextPromptIndex(current)
      setInputText(DEMO_PROMPTS[next])
      return next
    })
  }

  function selectSuggestedPrompt(prompt: string, index: number) {
    setPromptIndex(index)
    setInputText(prompt)
  }

  async function runAction(label: string, action: () => Promise<void>) {
    setBusyAction(label)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusyAction(null)
    }
  }

  async function handleStartVision() {
    await runAction('startVision', async () => {
      await startVision()
      setStreamSrc(streamUrl())
      const status = await getVisionStatus()
      setVisionStatus(status)
      appendMessage('system', '视觉服务已启动。请靠近摄像头并挥手。只有近距离挥手才会开启对话。')
    })
  }

  async function handleStopVision() {
    await runAction('stopVision', async () => {
      await stopVision()
      const status = await getVisionStatus()
      setVisionStatus(status)
      appendMessage('system', '视觉服务已停止。')
    })
  }

  async function handleResetSession() {
    await runAction('resetSession', async () => {
      await stopVision().catch(() => undefined)
      const session = await resetSession()
      handledGreetingRef.current = null
      setVisionStatus(INITIAL_VISION_STATUS)
      setProfile(session.customer_profile)
      setRecommendedProducts([])
      setCompareIds([])
      setCompareRows([])
      setPromptIndex(0)
      setInputText(DEMO_PROMPTS[0])
      setMessages([
        {
          id: 'm-reset',
          role: 'agent',
          text: '会话已重置。请靠近屏幕并向我打招呼。',
        },
      ])
      setStreamSrc(streamUrl())
    })
  }

  async function handleDemoEvent(event: string, label: string) {
    await runAction(`demo-${event}`, async () => {
      const response = await sendDemoEvent(event)
      setProfile(response.customer_profile)
      const status = await getVisionStatus()
      setVisionStatus(status)
      appendMessage('system', label)
      if (event === 'wave' || event === 'greeting') {
        appendMessage('agent', WELCOME_MESSAGE)
        await sendDemoEvent('intro_finished')
      }
    })
  }

  async function handleVoiceHi() {
    await runAction('voiceHi', async () => {
      const result = await sendVoiceGreeting('你好')
      appendMessage('customer', '你好')
      appendMessage('agent', result.message)
      await sendDemoEvent('intro_finished')
      const session = await getSessionStatus()
      setProfile(session.customer_profile)
      const status = await getVisionStatus()
      setVisionStatus(status)
    })
  }

  async function handleChatSubmit() {
    const text = inputText.trim()
    if (!text) {
      return
    }

    await runAction('chat', async () => {
      appendMessage('customer', text)
      const response = await sendChat(text)
      appendMessage('agent', response.answer)
      setRecommendedProducts(response.recommended_products)
      setProfile(response.customer_profile)
      advanceSuggestedPrompt()
    })
  }

  async function handleCompareToggle(productId: string) {
    const nextIds = compareIds.includes(productId)
      ? compareIds.filter((id) => id !== productId)
      : [...compareIds, productId].slice(-2)

    setCompareIds(nextIds)
    if (nextIds.length === 2) {
      await runAction('compare', async () => {
        const result = await compareProducts(nextIds)
        setCompareRows(result.comparison)
      })
    } else {
      setCompareRows([])
    }
  }

  return (
    <main className="app-shell">
      <header className="hero-header">
        <div>
          <p className="eyebrow">Emergency Wood Floor Greeter Demo</p>
          <h1>木地板 AI 导购体验区</h1>
          <p className="subtitle">靠近屏幕并挥手，AI 导购会主动欢迎，并根据顾客需求推荐产品。</p>
        </div>
        <div className="server-card">
          <span>Backend</span>
          <strong>{API_BASE_URL}</strong>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="dashboard-grid">
        <section className="panel camera-panel">
          <div className="panel-title-row">
            <div>
              <h2>摄像头与视觉检测</h2>
              <p>Backend OpenCV + MediaPipe 独占摄像头；只有 CLOSE + stable=True 的挥手会触发问候。</p>
            </div>
            <span className={`status-dot ${visionStatus.running ? 'on' : 'off'}`}>
              {visionStatus.running ? 'RUNNING' : 'STOPPED'}
            </span>
          </div>
          <div className="camera-frame">
            <img src={streamSrc} alt="Vision stream" />
          </div>
          <div className="status-grid">
            <Metric label="State" value={stateLabel(visionStatus.state)} highlight />
            <Metric label="Person" value={visionStatus.person_detected ? 'YES' : 'NO'} />
            <Metric label="Distance" value={visionStatus.distance} />
            <Metric label="Stable Close" value={visionStatus.stable_close ? 'TRUE' : 'FALSE'} />
            <Metric label="Face Height" value={formatPercent(visionStatus.face_height_ratio)} />
            <Metric label="Face Area" value={formatPercent(visionStatus.face_area_ratio)} />
            <Metric label="Accepted Wave" value={visionStatus.wave_detected ? 'YES' : 'NO'} />
            <Metric label="Raw Wave" value={visionStatus.raw_wave_event ?? 'NONE'} />
            <Metric label="Ignored" value={visionStatus.raw_wave_ignored_reason ?? 'NONE'} />
            <Metric label="FPS" value={visionStatus.fps_estimate.toFixed(1)} />
          </div>
        </section>

        <section className="panel chat-panel">
          <div className="panel-title-row">
            <div>
              <h2>AI 导购对话</h2>
              <p>当前阶段先支持文本输入和模拟语音问候；下一步接入浏览器语音。</p>
            </div>
            <span className="status-dot neutral">TEXT MODE</span>
          </div>
          <div className="chat-log">
            {messages.map((message) => (
              <div key={message.id} className={`message ${message.role}`}>
                <span>{message.role === 'agent' ? 'AI 导购' : message.role === 'customer' ? '顾客' : '系统'}</span>
                <p>{message.text}</p>
              </div>
            ))}
          </div>
          <div className="quick-prompts">
            {DEMO_PROMPTS.map((prompt, index) => (
              <button
                key={prompt}
                type="button"
                className={`prompt-chip ${index === promptIndex ? 'active' : ''}`}
                onClick={() => selectSuggestedPrompt(prompt, index)}
                disabled={busyAction !== null}
              >
                {prompt}
              </button>
            ))}
          </div>
          <div className="chat-input-row">
            <textarea
              value={inputText}
              onChange={(event) => setInputText(event.target.value)}
              placeholder="输入顾客问题，例如：家里有宠物，哪种地板好打理？"
            />
            <button type="button" onClick={handleChatSubmit} disabled={busyAction !== null}>
              发送问题
            </button>
          </div>
        </section>
      </section>

      <section className="panel controls-panel">
        <div className="panel-title-row">
          <div>
            <h2>Demo Controls</h2>
            <p>现场演示时用于兜底：即使摄像头或语音不稳定，也能完成完整流程。</p>
          </div>
          {busyAction && <span className="status-dot neutral">BUSY: {busyAction}</span>}
        </div>
        <div className="button-grid">
          <button type="button" onClick={handleStartVision} disabled={busyAction !== null}>
            Start Vision
          </button>
          <button type="button" onClick={handleStopVision} disabled={busyAction !== null}>
            Stop Vision
          </button>
          <button
            type="button"
            onClick={() => void handleDemoEvent('person_close', '模拟顾客已靠近。')}
            disabled={busyAction !== null}
          >
            Simulate Close
          </button>
          <button
            type="button"
            onClick={() => void handleDemoEvent('wave', '模拟顾客挥手问候。')}
            disabled={busyAction !== null}
          >
            Simulate Wave
          </button>
          <button type="button" onClick={handleVoiceHi} disabled={busyAction !== null}>
            Simulate Voice Hi
          </button>
          <button type="button" onClick={handleResetSession} disabled={busyAction !== null}>
            Reset Session
          </button>
        </div>
      </section>

      <section className="lower-grid">
        <section className="panel products-panel">
          <div className="panel-title-row">
            <div>
              <h2>模拟产品库与推荐</h2>
              <p>点击产品可选择两款做对比；AI 推荐会自动高亮。</p>
            </div>
            <span className="status-dot neutral">{products.length} SKUs</span>
          </div>
          <div className="product-grid">
            {products.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                recommended={recommendedIds.has(product.id)}
                selected={compareIds.includes(product.id)}
                onToggleCompare={() => void handleCompareToggle(product.id)}
              />
            ))}
          </div>
          {compareRows.length > 0 && (
            <div className="compare-table-wrap">
              <h3>产品对比</h3>
              <table>
                <tbody>
                  {compareRows.map((row) => (
                    <tr key={row.field}>
                      <th>{row.field}</th>
                      {compareIds.map((id) => (
                        <td key={id}>{String(row.values[id] ?? '-')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel profile-panel">
          <div className="panel-title-row">
            <div>
              <h2>客户需求摘要</h2>
              <p>后端根据对话自动提取需求，模拟销售侧建档。</p>
            </div>
            <span className="status-dot neutral">{profile.follow_up_status}</span>
          </div>
          <div className="profile-list">
            <InfoRow label="房间" value={profile.room_type ?? '待确认'} />
            <InfoRow label="风格" value={profile.style ?? '待确认'} />
            <InfoRow label="预算" value={profile.budget ?? '待确认'} />
            <InfoRow label="特殊需求" value={profile.special_needs.length ? profile.special_needs.join(' / ') : '待确认'} />
            <InfoRow label="关注点" value={profile.concerns.length ? profile.concerns.join(' / ') : '待确认'} />
            <InfoRow
              label="推荐 SKU"
              value={profile.recommended_product_ids.length ? profile.recommended_product_ids.join(' / ') : '暂无'}
            />
          </div>
          <div className="summary-card">
            <h3>Conversation Summary</h3>
            <p>{profile.conversation_summary || '客户需求尚未明确。'}</p>
          </div>
          <div className="summary-card">
            <h3>Follow-up Suggestion</h3>
            <p>{profile.follow_up_suggestion || '建议继续确认铺装空间、风格和预算。'}</p>
          </div>
        </section>
      </section>
    </main>
  )
}

function Metric({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className={`metric ${highlight ? 'highlight' : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ProductCard({
  product,
  recommended,
  selected,
  onToggleCompare,
}: {
  product: FlooringProduct
  recommended: boolean
  selected: boolean
  onToggleCompare: () => void
}) {
  return (
    <article className={`product-card ${recommended ? 'recommended' : ''} ${selected ? 'selected' : ''}`}>
      <div className="product-card-header">
        <div>
          <span className="sku">{product.id}</span>
          <h3>{product.name}</h3>
        </div>
        {recommended && <span className="badge">推荐</span>}
      </div>
      <div className="product-meta">
        <span>{product.type}</span>
        <span>{product.color}</span>
        <span>{product.price_range}</span>
        <span>{product.wear_level}</span>
      </div>
      <p className="product-points">{product.selling_points.slice(0, 3).join(' / ')}</p>
      <div className="feature-row">
        <span>防水：{yesNo(product.waterproof)}</span>
        <span>地暖：{yesNo(product.floor_heating)}</span>
        <span>宠物：{yesNo(product.pet_friendly)}</span>
      </div>
      <button type="button" className="secondary-button" onClick={onToggleCompare}>
        {selected ? '取消对比' : '加入对比'}
      </button>
    </article>
  )
}

export default App
