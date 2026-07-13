(() => {
  function isEnglish() {
    return window.__WOODFLOOR_LANGUAGE__ === 'en' || window.localStorage.getItem('woodfloor_ui_language') === 'en'
  }

  const exact = new Map(Object.entries({
    '返回导购': 'Back to consultant',
    '方案发送与授权': 'Plan delivery and consent',
    '获取本次方案与后续联系': 'Get My Plan and Follow-Up',
    '联系方式完全自愿，只保存在运行此 Demo 的本机数据库。针对本次方案的联系授权与长期新品、优惠信息授权是两个独立选项。': 'Providing contact details is voluntary. They are stored only in this demo’s local database. Consent for follow-up on this consultation and consent for long-term product or promotion messages are separate choices.',
    '本次咨询摘要': 'Consultation summary',
    '正在读取当前咨询 Session…': 'Loading the current consultation session…',
    '真实联系方式不会发送给 Terra、Qwen 或任何 LLM。LLM 最多只知道“客户是否已经授权联系”，不会看到手机号、微信号、邮箱或客户姓名。': 'Actual contact details are never sent to Terra, Qwen or any LLM. The model can know only whether follow-up consent exists; it cannot see a phone number, messaging ID, email address or customer name.',
    '已保存联系授权': 'Saved contact consent',
    '保留本次联系，关闭营销推送': 'Keep consultation follow-up; disable marketing',
    '撤回全部主动联系授权': 'Withdraw all proactive-contact consent',
    '永久删除联系方式和跟进记录': 'Permanently delete contact and follow-up records',
    '称呼（可选）': 'Preferred name (optional)',
    '联系方式类型': 'Contact method',
    '手机': 'Phone',
    '微信': 'WeChat',
    '邮箱': 'Email',
    '联系方式': 'Contact details',
    '方便联系的时间（可选）': 'Preferred contact time (optional)',
    '本次联系用途': 'Purpose of this follow-up',
    '发送本次选购方案': 'Send this flooring plan',
    '跟进报价与样板': 'Follow up on quotation and samples',
    '预约到店或测量': 'Arrange a store visit or measurement',
    '本次方案联系授权（必选）': 'Consultation follow-up consent (required)',
    '我同意门店仅为发送本次方案、报价、样板或到店安排而联系我。我可以随时撤回并删除数据。': 'I consent to the store contacting me only to send this plan, discuss a quotation or samples, or arrange a store visit. I may withdraw consent and delete the data at any time.',
    '新品与优惠信息授权（可选）': 'New product and promotion consent (optional)',
    '我另外同意接收后续新品和优惠信息。未勾选不会影响获取本次方案。': 'I separately consent to receiving future product and promotion information. Leaving this unchecked does not affect access to this consultation plan.',
    '保存授权并安排后续': 'Save consent and arrange follow-up',
    '暂不留下联系方式': 'Do not provide contact details',
    'Demo 默认在授权后三天生成一次本地跟进提醒。它不会自动发送短信、微信或邮件；门店人员必须在本地工作台确认后执行。': 'The demo creates a local follow-up reminder three days after consent. It does not automatically send a text message, WeChat message or email; store staff must review it in the local workbench.',
    '请输入手机号': 'Enter a phone number',
    '请输入微信号': 'Enter a WeChat ID',
    '请输入邮箱': 'Enter an email address',
    '例如：工作日下午 3 点后': 'For example: weekdays after 3 pm',
    '正在本机保存授权和联系方式…': 'Saving consent and contact details on this PC…',
    '查看并删除我的本地数据': 'View and delete my local data',
    '系统会先通过当前摄像头验证您是否与本机保存的客户记录匹配。只有验证成功并再次明确确认后，才会永久删除对应数据。': 'The system first uses the current camera to verify a match with a locally stored customer record. Data is permanently deleted only after a successful match and a second explicit confirmation.',
    '人脸特征模板': 'Face-feature templates',
    '删除本机保存的 SFace 特征向量。系统默认不保存原始人脸照片。': 'Delete the SFace feature vectors stored on this PC. Raw face photos are not stored by default.',
    '客户选购档案': 'Customer flooring profile',
    '删除房间、预算、风格、颜色、家庭使用条件和推荐结果等结构化信息。': 'Delete structured room, budget, style, colour, household-condition and recommendation information.',
    '历史咨询记录': 'Consultation history',
    '删除该客户关联的历次会话摘要及完整对话轮次。': 'Delete all session summaries and complete dialogue turns associated with this customer.',
    '为避免他人误删数据，系统不会在验证前展示姓名或历史咨询内容。候选身份令牌只保存在当前页面内存中，不写入浏览器存储。': 'To prevent deletion by another person, no name or history is shown before verification. The candidate identity token is kept only in this page’s memory and is not written to browser storage.',
    '第一步：验证当前用户': 'Step 1: Verify the current user',
    '请正对摄像头、保持光线充足，然后点击下面的按钮。验证本身不会修改或删除任何数据。': 'Face the camera in good lighting, then select the button below. Verification itself does not modify or delete any data.',
    '验证并查找我的本地数据': 'Verify and find my local data',
    '取消并返回': 'Cancel and return',
    '第二步：确认永久删除': 'Step 2: Confirm permanent deletion',
    '系统已找到可信的本地候选记录。为保护隐私，删除前仍不会显示该记录的姓名或咨询内容。': 'A trusted local candidate record was found. To protect privacy, its name and consultation content are still hidden before deletion.',
    '删除后，下一次将把您视为新客户。': 'After deletion, the next visit will be treated as a new customer.',
    '删除后可以重新演示“同意并注册本地记忆”的完整流程。': 'After deletion, the full consent and local-memory enrolment flow can be demonstrated again.',
    '此操作不可撤销。': 'This action cannot be undone.',
    '我确认这是我的本地数据，并要求永久删除人脸特征、客户档案和全部历史咨询记录。': 'I confirm that this is my local data and request permanent deletion of face features, customer profile and all consultation history.',
    '永久删除我的本地数据': 'Permanently delete my local data',
    '重新验证': 'Verify again',
    '删除操作仅作用于运行此 Demo 的本地 SQLite 客户记忆数据库。': 'Deletion affects only the local SQLite customer-memory database used by this demo.',
    '门店销售工作台': 'Store sales workbench',
    '销售线索与跟进提醒': 'Sales leads and follow-up reminders',
    '刷新': 'Refresh',
    '全部有效线索': 'All active leads',
    '到期提醒': 'Due reminders',
    '联系授权': 'Contact consent',
    '营销授权': 'Marketing consent',
    '客户需求': 'Customer requirements',
    '跟进状态': 'Follow-up status',
    '下一次跟进': 'Next follow-up',
    '保存跟进': 'Save follow-up',
    '待发送方案': 'Plan pending',
    '已发送方案': 'Plan sent',
    '待报价': 'Quotation pending',
    '待回访': 'Follow-up pending',
    '客户考虑中': 'Customer considering',
    '已预约到店': 'Store visit booked',
    '已完成': 'Completed',
    '已关闭': 'Closed',
    '已撤回': 'Withdrawn',
    '冷': 'Cold',
    '温': 'Warm',
    '热': 'Hot'
  }))

  function translate(value) {
    if (!isEnglish() || typeof value !== 'string') return value
    const leading = value.match(/^\s*/)?.[0] || ''
    const trailing = value.match(/\s*$/)?.[0] || ''
    let text = value.trim()
    if (!text) return value
    if (exact.has(text)) return leading + exact.get(text) + trailing

    text = text
      .replace(/^读取 Session 失败：/, 'Failed to load session: ')
      .replace(/^更新授权失败：/, 'Failed to update consent: ')
      .replace(/^保存失败：/, 'Failed to save: ')
      .replace(/^删除失败：/, 'Failed to delete: ')
      .replace(/^验证失败：/, 'Verification failed: ')
      .replace(/^正在启动摄像头并进行多帧本地人脸验证，请正对屏幕并保持不动…$/, 'Starting the camera and performing multi-frame local face verification. Face the screen and remain still…')
      .replace(/^已找到可信的本地候选记录。请阅读删除范围并完成第二次明确确认。$/, 'A trusted local candidate record was found. Review the deletion scope and provide the second explicit confirmation.')
      .replace(/^正在永久删除本地人脸特征、客户档案和历史咨询记录…$/, 'Permanently deleting local face features, customer profile and consultation history…')
      .replace(/^您的本地数据已永久删除。系统下一次识别时会将您视为新客户，现在可以返回导购并重新演示注册流程。$/, 'Your local data has been permanently deleted. The next recognition attempt will treat you as a new customer, so the enrolment flow can now be demonstrated again.')

    if (/^[\u4e00-\u9fff]/.test(text) && text.includes('；本次联系授权：')) {
      return leading + 'A saved contact record is associated with this session. Consent and follow-up status are shown according to the current local CRM record.' + trailing
    }
    return leading + text + trailing
  }

  function process(root) {
    if (!isEnglish()) return
    if (root.nodeType === Node.TEXT_NODE) {
      const translated = translate(root.nodeValue || '')
      if (translated !== root.nodeValue) root.nodeValue = translated
      return
    }
    if (!(root instanceof Element) && root !== document) return
    if (root instanceof Element) {
      for (const attribute of ['placeholder', 'aria-label', 'title']) {
        const value = root.getAttribute(attribute)
        if (value) root.setAttribute(attribute, translate(value))
      }
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT)
    let node = walker.nextNode()
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        const translated = translate(node.nodeValue || '')
        if (translated !== node.nodeValue) node.nodeValue = translated
      } else if (node instanceof Element) {
        for (const attribute of ['placeholder', 'aria-label', 'title']) {
          const value = node.getAttribute(attribute)
          if (value) node.setAttribute(attribute, translate(value))
        }
      }
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
