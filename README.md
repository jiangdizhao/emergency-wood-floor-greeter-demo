# Emergency Wood Floor Greeter Demo

面向木地板门店的双语虚拟导购 Demo，包含：

- 一键中文/英文切换；
- 浏览器语音识别、文字输入和 Kokoro 本地中英文语音合成；
- GPT-5.6 Terra 云端模式与 Qwen 3.5 本地模式两套平行 LLM 架构；
- 本地确定性产品推荐、产品对比、高级销售策略和受控促销；
- OpenCV + MediaPipe 后台视觉服务；
- YuNet + SFace 本地人脸注册、回访识别和历史记忆恢复；
- 本地 SQLite CRM、联系方式授权和跟进提醒；
- 用户自助删除本地人脸特征、客户档案、联系方式和历史咨询记录。

---

# 重要架构原则

Terra 和 Qwen 是两套相互独立的运行模式：

```text
Terra 模式
Terra 解析客户意图
→ Backend 校验并更新客户状态
→ 本地确定性推荐产品
→ Terra 生成自然语言回答

Qwen 模式
Qwen 解析客户意图
→ Backend 校验并更新客户状态
→ 本地确定性推荐产品
→ Qwen 生成自然语言回答
```

两种模式均遵守：

- LLM 不直接修改数据库；
- LLM 不直接选择产品 SKU；
- 产品数据库、客户档案、人脸特征和 CRM 数据保存在本机；
- Terra 只接收生成当前回答所需的最小上下文；
- 联系方式不会发送给 Terra 或 Qwen；
- 不启用隐藏的 Terra ↔ Qwen 跨模型自动 fallback；
- 当前 Session 选择哪个 Provider，就始终使用该 Provider。

---

# 一、目录与运行环境

以下命令假设项目位于：

```text
F:\emergency-wood-floor-greeter-demo
```

Backend Conda 环境：

```text
smartoffice
```

Kokoro Conda 环境：

```text
kokoro-tts
```

完整程序通常使用 4 个 PowerShell Terminal：

```text
Terminal 1：Kokoro 本地 TTS，端口 8010
Terminal 2：Ollama，仅 Qwen 模式需要，端口 11434
Terminal 3：FastAPI Backend，端口 8000
Terminal 4：Vite Frontend，端口 5173
```

推荐启动顺序：

```text
Kokoro
→ Ollama（仅 Qwen）
→ Backend
→ Frontend
```

Terra 模式不需要 Ollama，因此可以省略 Terminal 2。

---

# 二、首次部署

## 1. 拉取代码

```powershell
cd F:\emergency-wood-floor-greeter-demo
git pull --ff-only
```

## 2. Backend Python 环境

```powershell
conda activate smartoffice
```

只在首次安装或 `requirements.txt` 更新后执行：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
python -m pip install -r requirements.txt
```

不要对已经正常工作的视觉环境执行 `--force-reinstall`。当前固定版本包括：

```text
mediapipe==0.10.13
numpy==2.4.6
opencv-python==4.13.0.92
```

## 3. 下载本地人脸模型

只需执行一次：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
powershell -ExecutionPolicy Bypass -File .\scripts\download_face_models.ps1
```

模型位置：

```text
backend/app/data/models/face_detection_yunet_2023mar.onnx
backend/app/data/models/face_recognition_sface_2021dec.onnx
```

## 4. 安装 Frontend 依赖

```powershell
cd F:\emergency-wood-floor-greeter-demo\ui
npm install
```

## 5. 准备 Qwen 模型

仅 Qwen 模式需要：

```powershell
ollama pull qwen3.5:4b
ollama list
```

应看到：

```text
qwen3.5:4b
```

---

# 三、Terminal 1：启动 Kokoro 本地 TTS

不要把 Kokoro 安装进 `smartoffice` 环境。它使用独立的 `kokoro-tts` 环境。

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts

powershell -ExecutionPolicy Bypass `
  -File .\start_kokoro_tts.ps1
```

启动脚本会主动定位：

```text
D:\anaconda3\envs\kokoro-tts\python.exe
```

当前默认语音配置：

```text
中文速度：0.84
英文速度：0.92
中文安全分块：88 字符
人工标点停顿：关闭
```

健康检查：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/health" `
  -Method Get |
ConvertTo-Json -Depth 30
```

重点检查：

```text
version = 0.5.1
warmup_ready = true
default_zh_speed = 0.84
default_en_speed = 0.92
clause_pause_ms = 0
sentence_pause_ms = 0
```

中文声音：

```text
zm_yunxi
zm_yunjian
zm_yunxia
zm_yunyang
```

英文声音：

```text
am_liam
am_michael
am_puck
am_onyx
```

长中文介绍验证：

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts

& "D:\anaconda3\envs\kokoro-tts\python.exe" `
  .\verify_long_mandarin_intro.py
```

成功时应显示：

```text
PASS: long Mandarin text uses safe chunks, slower speech, and no artificial punctuation pauses.
```

---

# 四、Terminal 3：启动 Backend

## Backend 启动的关键规则

1. Provider、模型、API Key 和 timeout 等环境变量，必须在启动 Backend 的同一个 PowerShell 进程中设置。
2. 修改环境变量后，必须停止并重新启动 Backend。
3. `DEFAULT_DIALOGUE_PROVIDER` 只影响之后新创建的 Session；切换模式后应在前端点击“重新开始”。
4. 不要只执行：

```powershell
$secureKey = Read-Host "OpenAI API key" -AsSecureString
```

这一步只创建 `$secureKey` 变量，并不会自动设置 `OPENAI_API_KEY`。
5. 不要把真实 API Key 写进 README、代码、脚本、`.env` 或 Git。

---

## 方案 A：GPT-5.6 Terra 云端模式

### 推荐启动方式：使用安全启动脚本

这是最稳妥的 Terra 启动方法。脚本会：

- 使用安全输入框读取 API Key；
- 将 Key 注入当前 Backend 进程；
- 不打印 Key 内容；
- 设置 `DEFAULT_DIALOGUE_PROVIDER=terra`；
- 设置 `OPENAI_DIALOGUE_MODEL=gpt-5.6-terra`；
- 设置解析和生成 timeout；
- 使用 `smartoffice` 环境中的 Python 启动 Uvicorn；
- Key 为空时直接拒绝启动。

执行：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_backend_terra.ps1
```

出现提示后粘贴 API Key：

```text
OpenAI API key: ********
```

正常启动时应显示：

```text
Starting Backend in Terra mode...
Python: D:\anaconda3\envs\smartoffice\python.exe
Model: gpt-5.6-terra
OPENAI_API_KEY: configured (value hidden)
Local TTS: http://127.0.0.1:8010/tts
```

脚本默认等价于：

```text
Provider: terra
Model: gpt-5.6-terra
Parse timeout: 12 seconds
Render timeout: 15 seconds
Host: 127.0.0.1
Port: 8000
Reload: enabled
```

自定义 timeout：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_backend_terra.ps1 `
  -ParseTimeoutSeconds 20 `
  -RenderTimeoutSeconds 25
```

关闭自动 reload：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_backend_terra.ps1 `
  -NoReload
```

明确指定 Python：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_backend_terra.ps1 `
  -PythonExe "D:\anaconda3\envs\smartoffice\python.exe"
```

### 手动启动 Terra

只有在调试启动脚本时才建议使用手动方式。

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate smartoffice

$secureKey = Read-Host "OpenAI API key" -AsSecureString

$env:OPENAI_API_KEY = `
  [System.Net.NetworkCredential]::new("", $secureKey).Password

Remove-Variable secureKey

$env:DEFAULT_DIALOGUE_PROVIDER="terra"
$env:OPENAI_DIALOGUE_MODEL="gpt-5.6-terra"
$env:OPENAI_PARSE_TIMEOUT_SECONDS="12"
$env:OPENAI_RENDER_TIMEOUT_SECONDS="15"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"

$env:LOCAL_TTS_URL="http://127.0.0.1:8010/tts"
$env:LOCAL_TTS_HEALTH_URL="http://127.0.0.1:8010/health"

if ($env:OPENAI_API_KEY) {
    Write-Host "OPENAI_API_KEY is set"
} else {
    throw "OPENAI_API_KEY is missing"
}

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

可选项目或组织配置，仅在账户明确要求时设置：

```powershell
$env:OPENAI_PROJECT_ID="your-project-id"
$env:OPENAI_ORG_ID="your-organization-id"
```

### 检查 Terra Provider

在另一个 PowerShell 中执行：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/llm/status" `
  -Method Get |
ConvertTo-Json -Depth 30
```

应看到：

```text
providers.terra.configured = true
providers.terra.available = true
providers.terra.model = gpt-5.6-terra
```

如果看到：

```text
OPENAI_API_KEY is not configured for Terra mode
```

说明 Key 没有进入启动 Uvicorn 的进程。停止 Backend，并使用 `start_backend_terra.ps1` 重新启动。

### 确认新 Session 使用 Terra

```powershell
$body = @{
  provider_mode = $null
} | ConvertTo-Json

$session = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/identity/session/new" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body

$session | ConvertTo-Json -Depth 20
```

应看到：

```text
provider_mode = terra
provider_label = Cloud Intelligence · Terra
```

### Terra 常见错误

#### `OPENAI_API_KEY is not configured`

原因：

- 只读取了 `$secureKey`，没有设置 `$env:OPENAI_API_KEY`；
- Key 在另一个 PowerShell 中设置；
- 设置 Key 后没有重启 Backend；
- Uvicorn reload 子进程启动前环境变量已丢失。

解决：

```powershell
Ctrl+C

powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_backend_terra.ps1
```

#### `OpenAI HTTP 401`

通常表示 Key 无效、过期或粘贴错误。重新启动脚本并重新输入 Key。

#### `OpenAI HTTP 403`

通常表示项目、组织或模型权限问题。检查账户是否有权访问指定模型，并确认可选的 `OPENAI_PROJECT_ID` 或 `OPENAI_ORG_ID` 是否正确。

#### `OpenAI HTTP 404`

通常表示模型名或 Base URL 不正确。当前 Demo 默认：

```text
OPENAI_DIALOGUE_MODEL = gpt-5.6-terra
OPENAI_BASE_URL = https://api.openai.com/v1
```

#### `OpenAI request failed: ... timeout`

提高 timeout：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_backend_terra.ps1 `
  -ParseTimeoutSeconds 25 `
  -RenderTimeoutSeconds 30
```

---

## 方案 B：Qwen 3.5 本地模式

### 启动或检查 Ollama

如果 Windows Ollama 桌面程序已经运行，不要再启动第二个服务。

检查：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:11434/api/tags" `
  -Method Get |
ConvertTo-Json -Depth 20

ollama list
ollama ps
```

如果 Ollama 尚未运行：

```powershell
$env:OLLAMA_MODELS="F:\ollama-models"
$env:OLLAMA_CONTEXT_LENGTH="4096"
$env:OLLAMA_MAX_LOADED_MODELS="1"
$env:OLLAMA_NUM_PARALLEL="1"
$env:OLLAMA_KEEP_ALIVE="30m"
$env:OLLAMA_NO_CLOUD="1"

ollama serve
```

### 以 Qwen 模式启动 Backend

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate smartoffice

$env:DEFAULT_DIALOGUE_PROVIDER="qwen"
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:OLLAMA_DIALOGUE_MODEL="qwen3.5:4b"
$env:OLLAMA_NUM_CTX="4096"
$env:OLLAMA_KEEP_ALIVE="30m"
$env:OLLAMA_PARSE_TIMEOUT_SECONDS="20"
$env:OLLAMA_RENDER_TIMEOUT_SECONDS="15"

$env:LOCAL_TTS_URL="http://127.0.0.1:8010/tts"
$env:LOCAL_TTS_HEALTH_URL="http://127.0.0.1:8010/health"

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

关键选择变量：

```powershell
$env:DEFAULT_DIALOGUE_PROVIDER="qwen"
```

即使当前 PowerShell 中存在 `OPENAI_API_KEY`，显式选择 `qwen` 后，新 Session 仍使用 Qwen。

检查：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/llm/status" `
  -Method Get |
ConvertTo-Json -Depth 30
```

应看到：

```text
providers.qwen.available = true
providers.qwen.model = qwen3.5:4b
providers.qwen.model_present = true
```

确认新 Session：

```powershell
$body = @{
  provider_mode = $null
} | ConvertTo-Json

$session = Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/identity/session/new" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body

$session | ConvertTo-Json -Depth 20
```

应看到：

```text
provider_mode = qwen
provider_label = Private Local AI · Qwen 3.5
```

---

# 五、Terminal 4：启动 Frontend

先确认 Kokoro 与 Backend 已启动：

```powershell
cd F:\emergency-wood-floor-greeter-demo\ui

$env:VITE_API_BASE_URL="http://127.0.0.1:8000"

npm run dev -- --host 127.0.0.1
```

打开：

```text
http://127.0.0.1:5173/
```

推荐浏览器：

```text
Google Chrome
Microsoft Edge
```

语音识别依赖浏览器 Web Speech API。

更新前端或切换语言后：

```text
1. Ctrl+C 停止旧 Vite
2. 重新运行 npm run dev
3. 关闭旧浏览器标签
4. 重新打开页面
5. Ctrl+F5 强制刷新
```

---

# 六、在 Terra 和 Qwen 之间切换

推荐方式是停止 Backend，然后按目标模式重新启动。

## Qwen → Terra

```powershell
# 在 Backend Terminal 中按 Ctrl+C

cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_backend_terra.ps1
```

## Terra → Qwen

```powershell
# 在 Backend Terminal 中按 Ctrl+C

cd F:\emergency-wood-floor-greeter-demo\backend
conda activate smartoffice

$env:DEFAULT_DIALOGUE_PROVIDER="qwen"
$env:OLLAMA_DIALOGUE_MODEL="qwen3.5:4b"
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

切换后在前端点击：

```text
重新开始
```

或刷新欢迎页创建新 Session。

不建议在客户的实际会话中途切换 Provider。

---

# 七、一键检查服务状态

## Backend

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/health" `
  -Method Get |
ConvertTo-Json -Depth 30
```

## LLM

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/llm/status" `
  -Method Get |
ConvertTo-Json -Depth 30
```

## Vision

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/vision/status" `
  -Method Get |
ConvertTo-Json -Depth 30
```

## Face identity

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/identity/status" `
  -Method Get |
ConvertTo-Json -Depth 30
```

期望：

```text
model.available = true
vision.camera_opened = true
stores_raw_photos = false
requires_confirmation = true
```

## Kokoro

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/health" `
  -Method Get |
ConvertTo-Json -Depth 30
```

## Backend TTS 代理

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/tts/status" `
  -Method Get |
ConvertTo-Json -Depth 30
```

## Ollama，仅 Qwen

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:11434/api/tags" `
  -Method Get |
ConvertTo-Json -Depth 30
```

---

# 八、Smoke tests

## 高级销售 Phase 1

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_senior_sales.ps1
```

## 销售 Phase 2/3 与 CRM

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_sales_phase2_3.ps1
```

## 双语 UI 与语音

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_bilingual.ps1
```

## 平行 LLM

Qwen：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_parallel_llm.ps1 `
  -ProviderMode qwen
```

Terra：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_parallel_llm.ps1 `
  -ProviderMode terra
```

## 人脸身份 MVP

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_face_identity.ps1 `
  -ProviderMode terra `
  -RunRecognition
```

没有已注册客户时：

```text
status = no_enrolled_customers
```

属于正常结果。

---

# 九、本地数据、CRM 与隐私

本地数据库：

```text
backend/app/data/customer_memory.db
```

保存：

- 客户结构化需求；
- 本地 SFace 特征向量；
- 会话摘要；
- 联系授权；
- CRM 跟进状态和提醒。

默认行为：

- 不保存原始人脸照片；
- 未经确认不恢复历史；
- 确认前不显示姓名和历史；
- 联系方式不会发送给 LLM；
- `customer_id` 与 `session_id` 分离；
- 每次到店创建新的 Session；
- 功能仅用于低风险导购连续性，不用于付款、门禁或法律身份验证。

用户数据删除页面：

```text
http://127.0.0.1:5173/delete-my-data.html
```

本地 CRM 工作台：

```text
http://127.0.0.1:5173/crm-workbench.html
```

CRM 工作台当前没有生产级身份认证，只能用于本机 Demo，不得暴露到公网。

---

# 十、常见问题

## 1. Terra 显示“云端智能服务暂时不可用”

先看 Backend 日志。

若日志为：

```text
OPENAI_API_KEY is not configured for Terra mode
```

执行：

```powershell
Ctrl+C

cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_backend_terra.ps1
```

不要只读取 `$secureKey` 而不设置 `$env:OPENAI_API_KEY`。

## 2. Qwen 显示 `Ollama request failed`

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:11434/api/tags" `
  -Method Get

ollama list
ollama ps
```

确认模型名：

```text
qwen3.5:4b
```

## 3. Kokoro 仍有旧语速或旧停顿

检查：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/health" `
  -Method Get |
ConvertTo-Json -Depth 30
```

应看到：

```text
version = 0.5.1
clause_pause_ms = 0
sentence_pause_ms = 0
```

如果不是，端口 8010 仍运行旧进程：

```powershell
Get-NetTCPConnection -LocalPort 8010 -State Listen |
Select-Object LocalAddress, LocalPort, OwningProcess
```

确认后停止旧进程，再启动新版 Kokoro。

## 4. 切换 Provider 后仍使用旧模式

```text
1. Ctrl+C 停止 Backend
2. 按目标模式重新启动 Backend
3. 检查 /api/llm/status
4. 前端点击“重新开始”
5. Ctrl+F5 强制刷新
```

## 5. 人脸模型不可用

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
powershell -ExecutionPolicy Bypass -File .\scripts\download_face_models.ps1
```

然后重启 Backend。

## 6. 浏览器语音识别没有内容

- 使用 Chrome 或 Edge；
- 检查麦克风权限；
- 点击“点击说话”；
- 说完完整句子；
- 点击“停止说话”；
- 更新前端后使用 `Ctrl+F5`。

---

# 十一、主要地址

```text
Frontend:
http://127.0.0.1:5173/

联系方式授权:
http://127.0.0.1:5173/follow-up.html

用户数据删除:
http://127.0.0.1:5173/delete-my-data.html

CRM 工作台:
http://127.0.0.1:5173/crm-workbench.html

Backend API:
http://127.0.0.1:8000/

FastAPI Docs:
http://127.0.0.1:8000/docs

Backend Health:
http://127.0.0.1:8000/api/health

LLM Status:
http://127.0.0.1:8000/api/llm/status

Vision Status:
http://127.0.0.1:8000/api/vision/status

Face Identity Status:
http://127.0.0.1:8000/api/identity/status

TTS Status:
http://127.0.0.1:8000/api/tts/status

Ollama:
http://127.0.0.1:11434

Kokoro:
http://127.0.0.1:8010
```

## More docs

- Local Kokoro setup: `local_tts/README.md`
- OpenAI TTS setup: `backend/OPENAI_TTS_SETUP.md`
- Senior sales Phase 1: `backend/SENIOR_SALES_PHASE1.md`
- Sales Phase 2/3: `backend/SALES_PHASE2_3.md`
