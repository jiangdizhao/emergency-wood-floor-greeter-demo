# Emergency Wood Floor Greeter Demo

面向木地板门店的客户交互 Demo，包含：

- 中文语音识别与文字输入；
- Terra 云端模式和 Qwen 3.5 本地模式两套平行 LLM 架构；
- 本地确定性产品推荐与对比；
- Kokoro 本地中文语音合成；
- OpenCV + MediaPipe 视觉服务；
- YuNet + SFace 本地人脸注册、回访识别和历史记忆恢复；
- 用户自助删除本地人脸特征、客户档案和历史咨询记录。

## 重要架构原则

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

两种模式均遵守以下约束：

- LLM 不直接修改数据库；
- LLM 不直接选择产品 SKU；
- 产品数据库、客户档案和人脸特征保存在本机；
- Terra 仅接收生成当前回答所需的最小上下文；
- 不启用隐藏的 Terra ↔ Qwen 跨模型自动 fallback；
- 当前 Session 使用哪个 Provider，就始终使用该 Provider。

---

# 一、首次部署

以下命令以项目位于：

```text
F:\emergency-wood-floor-greeter-demo
```

为例。

## 1. 拉取最新代码

```powershell
cd F:\emergency-wood-floor-greeter-demo
git pull
```

## 2. Backend Python 环境

当前本机实际使用的环境示例为：

```powershell
conda activate smartoffice
```

如果你的环境仍命名为 `woodfloor`，把后续命令中的：

```powershell
conda activate smartoffice
```

替换为：

```powershell
conda activate woodfloor
```

只在新环境首次安装时执行：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
python -m pip install -r requirements.txt
```

不要对已经正常工作的视觉环境执行 `--force-reinstall`。当前验证过的固定版本为：

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

模型保存在：

```text
backend/app/data/models/face_detection_yunet_2023mar.onnx
backend/app/data/models/face_recognition_sface_2021dec.onnx
```

## 4. 安装 Frontend 依赖

只需首次执行，或 `package.json` 更新后执行：

```powershell
cd F:\emergency-wood-floor-greeter-demo\ui
npm install
```

## 5. 准备 Qwen 模型

只在使用 Qwen 模式时需要：

```powershell
ollama pull qwen3.5:4b
ollama list
```

应看到：

```text
qwen3.5:4b
```

---

# 二、启动顺序总览

完整程序通常使用 4 个 PowerShell Terminal：

```text
Terminal 1：Kokoro 本地 TTS
Terminal 2：Ollama，仅 Qwen 模式需要
Terminal 3：FastAPI Backend，并在这里选择 Terra 或 Qwen
Terminal 4：Vite Frontend
```

Terra 模式不要求 Ollama 运行，因此可以省略 Terminal 2。

推荐启动顺序：

```text
Kokoro
→ Ollama（仅 Qwen）
→ Backend
→ Frontend
```

---

# 三、Terminal 1：启动 Kokoro 本地 TTS

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
conda activate kokoro-tts
powershell -ExecutionPolicy Bypass -File .\start_kokoro_tts.ps1
```

健康检查：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/health" `
  -Method Get |
ConvertTo-Json -Depth 10
```

也可以运行自带 smoke test：

```powershell
cd F:\emergency-wood-floor-greeter-demo\local_tts
powershell -ExecutionPolicy Bypass -File .\smoke_test_kokoro_tts.ps1

powershell -ExecutionPolicy Bypass `
  -File .\smoke_test_kokoro_tts.ps1 `
  -Language zh `
  -OutFile .\kokoro_zh_test.wav
```

本 Demo 使用的中文男声包括：

```text
zm_yunxi
zm_yunjian
zm_yunxia
zm_yunyang
```

---

# 四、选择并启动 LLM

## 方案 A：Qwen 3.5 本地模式

适用特点：

- 全部 LLM 推理在本机执行；
- 不依赖 OpenAI 网络服务；
- 没有按次 API 成本；
- 受本机 GPU、显存和散热影响，响应速度和复杂语义理解弱于 Terra。

## Terminal 2：启动 Ollama

先检查 Ollama 是否已经运行：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:11434/api/tags" `
  -Method Get |
ConvertTo-Json -Depth 10
```

如果 Windows Ollama 桌面程序已经运行，不要再启动第二个服务。

如果 Ollama 尚未运行，可以打开新的 PowerShell，并执行：

```powershell
$env:OLLAMA_MODELS="F:\ollama-models"
$env:OLLAMA_CONTEXT_LENGTH="4096"
$env:OLLAMA_MAX_LOADED_MODELS="1"
$env:OLLAMA_NUM_PARALLEL="1"
$env:OLLAMA_KEEP_ALIVE="30m"
$env:OLLAMA_NO_CLOUD="1"

ollama serve
```

在另一个 Terminal 检查：

```powershell
ollama list
ollama ps
```

如果模型尚未下载：

```powershell
ollama pull qwen3.5:4b
```

## Terminal 3：以 Qwen 模式启动 Backend

所有环境变量必须在启动 `uvicorn` 的同一个 PowerShell 中设置：

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

最关键的选择命令是：

```powershell
$env:DEFAULT_DIALOGUE_PROVIDER="qwen"
```

即使当前 PowerShell 中存在 `OPENAI_API_KEY`，显式设置为 `qwen` 后，新创建的咨询 Session 仍使用 Qwen。

### 检查 Qwen Provider 状态

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/llm/status" `
  -Method Get |
ConvertTo-Json -Depth 20
```

在 `providers.qwen` 中应看到：

```text
available = true
model = qwen3.5:4b
model_present = true
```

创建一个临时新 Session，确认默认模式确实是 Qwen：

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

## 方案 B：GPT-5.6 Terra 云端模式

适用特点：

- 对复杂中文表达、否定、修正和上下文理解更稳定；
- 回答更自然；
- 需要互联网连接和 OpenAI API Key；
- 会产生 API 调用费用；
- 本地产品数据库、人脸向量和完整客户历史不会发送给 Terra。

Terra 模式不需要 Ollama，可以直接启动 Backend。

## Terminal 3：安全设置 API Key

不要把真实 Key 写入 README、代码、PowerShell 脚本或 Git。

在启动 Backend 的同一个 PowerShell 中执行：

```powershell
$secureKey = Read-Host "OpenAI API key" -AsSecureString

$env:OPENAI_API_KEY = `
  [System.Net.NetworkCredential]::new("", $secureKey).Password

Remove-Variable secureKey
```

检查 Key 是否已经设置，但不要打印 Key 内容：

```powershell
if ($env:OPENAI_API_KEY) {
    Write-Host "OPENAI_API_KEY is set"
} else {
    Write-Host "OPENAI_API_KEY is missing"
}
```

## 以 Terra 模式启动 Backend

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
conda activate smartoffice

$env:DEFAULT_DIALOGUE_PROVIDER="terra"
$env:OPENAI_DIALOGUE_MODEL="gpt-5.6-terra"
$env:OPENAI_PARSE_TIMEOUT_SECONDS="12"
$env:OPENAI_RENDER_TIMEOUT_SECONDS="15"

$env:LOCAL_TTS_URL="http://127.0.0.1:8010/tts"
$env:LOCAL_TTS_HEALTH_URL="http://127.0.0.1:8010/health"

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

最关键的选择命令是：

```powershell
$env:DEFAULT_DIALOGUE_PROVIDER="terra"
```

Terra 模型名称由以下变量指定：

```powershell
$env:OPENAI_DIALOGUE_MODEL="gpt-5.6-terra"
```

### 可选 OpenAI 项目配置

只有账户环境确实需要时才设置：

```powershell
$env:OPENAI_PROJECT_ID="your-project-id"
$env:OPENAI_ORG_ID="your-organization-id"
```

通常不需要修改：

```powershell
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
```

### 检查 Terra Provider 状态

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/llm/status" `
  -Method Get |
ConvertTo-Json -Depth 20
```

在 `providers.terra` 中应看到：

```text
configured = true
available = true
model = gpt-5.6-terra
```

创建一个临时新 Session，确认默认模式确实是 Terra：

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

---

# 五、Terminal 4：启动 Frontend

先确认 Kokoro 和 Backend 已经启动，再执行：

```powershell
cd F:\emergency-wood-floor-greeter-demo\ui

$env:VITE_API_BASE_URL="http://127.0.0.1:8000"

npm run dev -- --host 127.0.0.1
```

打开：

```text
http://127.0.0.1:5173/
```

推荐使用：

```text
Google Chrome
Microsoft Edge
```

因为语音识别依赖浏览器 Web Speech API。

每次切换 Terra/Qwen、更新前端代码或遇到旧页面状态时：

```text
1. Ctrl+C 停止旧 Vite
2. 重新运行 npm run dev
3. 关闭旧浏览器标签
4. 重新打开页面，或使用 Ctrl+F5 强制刷新
```

---

# 六、如何在 Terra 和 Qwen 之间切换

## 推荐方式：重启 Backend 并设置默认 Provider

从 Qwen 切换到 Terra：

```powershell
# 在 Backend Terminal 中先 Ctrl+C

$env:DEFAULT_DIALOGUE_PROVIDER="terra"
$env:OPENAI_DIALOGUE_MODEL="gpt-5.6-terra"

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

从 Terra 切换到 Qwen：

```powershell
# 在 Backend Terminal 中先 Ctrl+C

$env:DEFAULT_DIALOGUE_PROVIDER="qwen"
$env:OLLAMA_DIALOGUE_MODEL="qwen3.5:4b"

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

切换后，在前端点击：

```text
重新开始
```

或刷新欢迎页并创建新的咨询。

`DEFAULT_DIALOGUE_PROVIDER` 影响后续新创建的 Session，不会偷偷修改已经存在的 Session。

## 针对一个已知 Session 临时切换

仅用于调试。先获得实际 `session_id`，然后执行：

```powershell
$sessionId = "session-replace-with-real-id"

$body = @{
  session_id = $sessionId
  provider_mode = "qwen"
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/session/provider" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body |
ConvertTo-Json -Depth 20
```

切换到 Terra 时，将：

```powershell
provider_mode = "qwen"
```

改为：

```powershell
provider_mode = "terra"
```

不建议在客户的一次真实会话中途切换 Provider。展会演示时应从欢迎页重新创建 Session。

---

# 七、一键检查所有服务

## Backend

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/health" `
  -Method Get |
ConvertTo-Json -Depth 20
```

## LLM

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/llm/status" `
  -Method Get |
ConvertTo-Json -Depth 20
```

## Vision

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/vision/status" `
  -Method Get |
ConvertTo-Json -Depth 20
```

## Face identity

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/identity/status" `
  -Method Get |
ConvertTo-Json -Depth 30
```

期望看到：

```text
model.available = true
vision.camera_opened = true
stores_raw_photos = false
requires_confirmation = true
```

## Kokoro TTS

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/tts/status" `
  -Method Get |
ConvertTo-Json -Depth 20
```

## Ollama，仅 Qwen 模式

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:11434/api/tags" `
  -Method Get |
ConvertTo-Json -Depth 20
```

---

# 八、OpenAI TTS fallback

Kokoro 是首选 TTS。OpenAI TTS 只是可选 fallback。

如果 Backend Terminal 中已经设置：

```powershell
$env:OPENAI_API_KEY
```

可以继续配置：

```powershell
$env:OPENAI_TTS_MODEL="gpt-4o-mini-tts"
$env:OPENAI_TTS_VOICE="marin"
```

TTS `auto` 顺序为：

```text
Kokoro 本地 TTS
→ OpenAI TTS
→ 浏览器 SpeechSynthesis
```

不要提交真实 API Key。`.env` 文件已被 Git 忽略，但仍建议在 PowerShell Session 中临时设置。

---

# 九、本地人脸识别与客户记忆

MVP 使用：

```text
OpenCV YuNet：人脸检测和五点关键点
OpenCV SFace：人脸对齐与特征向量
SQLite：客户、模板、Session 和历史记录
```

数据库位置：

```text
backend/app/data/customer_memory.db
```

数据库及 WAL 文件不会提交到 Git。

## 人脸注册与回访测试流程

1. 启动摄像头、Kokoro、所选 LLM、Backend 和 Frontend。
2. 第一次访问时点击 **开始咨询**。
3. 完成咨询并点击 **结束并总结**。
4. 点击 **同意并保存本地记忆**。
5. 阅读隐私说明，勾选同意，正对摄像头完成采集。
6. 返回欢迎页，再次点击开始咨询。
7. 系统匹配成功后显示通用 **欢迎回来** 页面。
8. 选择：
   - **继续上次咨询**：恢复上次项目；
   - **开始新的选购项目**：只保留稳定家庭背景；
   - **这不是我**：按匿名新客户处理。

## 可选阈值

```powershell
$env:FACE_ACCEPT_THRESHOLD="0.45"
$env:FACE_DUPLICATE_THRESHOLD="0.50"
$env:FACE_MARGIN_THRESHOLD="0.04"
$env:FACE_RECOGNITION_SAMPLES="8"
$env:FACE_MIN_VOTES="3"
$env:FACE_ENROLLMENT_SAMPLES="10"
$env:FACE_CANDIDATE_TTL_SECONDS="180"
```

默认策略偏向：

```text
宁可偶尔认不出回访客户
也不要错误加载其他客户的历史数据
```

## 隐私行为

- 必须由客户明确勾选并点击注册；
- 默认不保存原始人脸照片；
- 只保存本地 SFace float32 特征向量；
- 人脸匹配结果只生成临时候选；
- 未经客户确认不会恢复历史；
- 确认前不显示姓名和历史内容；
- 每次到店创建新的 `session_id`；
- `customer_id` 和 `session_id` 分离；
- 本功能只用于低风险导购连续性，不用于付款、门禁或法律身份验证。

---

# 十、用户删除本地数据

主页面右下角点击：

```text
隐私与数据
```

或直接打开：

```text
http://127.0.0.1:5173/delete-my-data.html
```

删除流程：

```text
当前用户重新进行本地人脸验证
→ 找到可信候选记录
→ 用户第二次明确确认
→ 永久删除人脸特征、客户档案和全部历史咨询
```

删除后，如果数据库原来只有一个客户，则：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/identity/status" `
  -Method Get |
ConvertTo-Json -Depth 20
```

应看到：

```text
customer_count = 0
face_template_count = 0
```

之后可以重新演示完整的人脸注册流程。

---

# 十一、Smoke tests

## 平行 LLM Backend

Qwen：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend

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

Qwen：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_face_identity.ps1 `
  -ProviderMode qwen
```

Terra：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_face_identity.ps1 `
  -ProviderMode terra
```

包含现场人脸识别：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_face_identity.ps1 `
  -ProviderMode terra `
  -RunRecognition
```

没有已注册客户时返回：

```text
status = no_enrolled_customers
```

属于正常结果，不代表测试失败。

---

# 十二、常见问题

## 1. 切换 Provider 后前端仍使用旧模式

原因通常是：

- Backend 没有重启；
- 浏览器仍保留旧 Session；
- 环境变量设置在另一个 PowerShell 中；
- 使用了旧页面热更新状态。

处理：

```text
1. Ctrl+C 停止 Backend
2. 在同一个 Terminal 设置 DEFAULT_DIALOGUE_PROVIDER
3. 重新启动 uvicorn
4. 前端点击“重新开始”
5. Ctrl+F5 强制刷新
```

## 2. Qwen 模式显示 Ollama request failed

检查：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:11434/api/tags" `
  -Method Get

ollama list
ollama ps
```

确认模型名称完全一致：

```text
qwen3.5:4b
```

## 3. Terra 模式显示 OPENAI_API_KEY is not configured

Key 必须在启动 Backend 的同一个 PowerShell 中设置。

```powershell
if ($env:OPENAI_API_KEY) {
    Write-Host "OPENAI_API_KEY is set"
} else {
    Write-Host "OPENAI_API_KEY is missing"
}
```

设置后必须重启 Backend。

## 4. Kokoro 不可用

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8010/health" `
  -Method Get
```

确认 Kokoro 使用独立环境：

```powershell
conda activate kokoro-tts
```

不要把 Kokoro 安装进视觉 Backend 环境。

## 5. 人脸模型不可用

重新下载：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend
powershell -ExecutionPolicy Bypass -File .\scripts\download_face_models.ps1
```

然后重启 Backend。

## 6. 浏览器语音识别没有内容

- 使用 Chrome 或 Edge；
- 检查麦克风权限；
- 点击 **点击说话**；
- 说完完整句子；
- 再点击 **停止说话**；
- 更新前端后执行 `Ctrl+F5`。

---

# 十三、主要地址

```text
Frontend:
http://127.0.0.1:5173/

用户数据删除:
http://127.0.0.1:5173/delete-my-data.html

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
