# 高级销售顾问 Phase 1

本阶段把原来的“需求登记 + 推荐”流程升级为受 Backend 控制的高级销售顾问流程。

## 已实现能力

- 新客户开场会介绍顾问角色、门店定位、服务方法和四类特色方案。
- 第一项发现问题从“哪个房间”改为“最不愿意妥协的核心需求”。
- Backend 保存 `primary_purchase_driver`，并把它作为后续推荐解释的中心。
- 新增确定性的 `SalesConversationPolicy`，计算销售阶段、目标和下一最佳动作。
- 推荐结果明确区分“主推款”和“备选款”。
- Terra 与 Qwen 都必须说明实际价值和至少一个诚实取舍。
- LLM 只能使用 Backend 批准的公司、系列和产品信息，不能虚构折扣、库存、质保、认证或安装日期。

## 模拟数据

当前没有真实门店资料，因此以下文件使用可替换的模拟数据：

```text
backend/app/data/company_profile.json
backend/app/data/product_collections.json
```

替换真实数据时，保留现有 JSON 字段结构即可，不需要修改对话编排代码。

## 主要代码

```text
backend/app/services/sales_knowledge_service.py
backend/app/services/sales_conversation_policy.py
backend/app/services/dialogue_policy.py
backend/app/services/answer_plan_service.py
backend/app/services/dialogue_orchestrator.py
backend/app/llm/prompts.py
```

职责划分：

```text
LLM
→ 解析客户最新话语并自然表达

ValidationGuard
→ 校验语义动作，防止错误状态写入

SalesConversationPolicy
→ 决定当前销售阶段和下一最佳销售动作

RecommendationService
→ 本地确定性选择产品 SKU

AnswerPlanService
→ 组装主推款、备选款、特色系列、匹配原因和取舍
```

## 离线静态检查

不需要 OpenAI API Key，也不需要启动 Ollama。

### 推荐方式：PowerShell 包装脚本

该包装脚本默认通过 `conda run -n smartoffice` 执行，因此：

- 不依赖当前 PowerShell 是否执行过 `conda init`；
- 不会被子 PowerShell 的 profile 意外切换到 base Python；
- 不需要先执行 `conda activate smartoffice`。

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_senior_sales.ps1
```

如环境名称不是 `smartoffice`：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_senior_sales.ps1 `
  -CondaEnvironment your-environment-name
```

也可以明确指定正确环境中的 Python：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_senior_sales.ps1 `
  -PythonExecutable "D:\anaconda3\envs\smartoffice\python.exe"
```

### 已经在 smartoffice 环境中的直接执行方式

当当前提示符明确显示 `(smartoffice)`，并且下面命令返回的是该环境内的 Python 时：

```powershell
(Get-Command python).Source
python --version
```

可以直接执行：

```powershell
python .\scripts\static_check_senior_sales.py
```

### 不要这样激活环境

下面的命令不能可靠地修改当前 PowerShell 的环境：

```powershell
D:\anaconda3\Scripts\conda.exe activate smartoffice
```

`conda activate` 是 PowerShell shell integration 提供的函数，不是普通的 `conda.exe` 子命令。若确实需要在当前 PowerShell 激活环境，可执行：

```powershell
& "D:\anaconda3\shell\condabin\conda-hook.ps1"
conda activate smartoffice
```

或者完全跳过激活，使用：

```powershell
D:\anaconda3\Scripts\conda.exe run --no-capture-output `
  -n smartoffice `
  python .\scripts\static_check_senior_sales.py
```

该项目使用 Python 3.10+ 的类型语法。若误用 base Python 3.9，静态检查会直接显示当前解释器和版本，并提示切换到 `smartoffice`。

成功时应看到：

```text
Senior sales phase-one static check passed.
```

## 推荐人工测试流程

新建 Session 后，欢迎语应包含：

- 顾问的高级选购定位；
- 门店的特色方案；
- 对客户核心购买驱动的询问。

然后依次回答：

```text
耐磨最重要
客厅
预算中等
现代简约
```

预期结果：

- 系统先记录“耐磨”为首要购买驱动；
- 信息足够后自动推荐，不需要客户再次催促；
- 回答明确说出主推款和备选款；
- 回答解释与耐磨、客厅、预算等条件的关系；
- 回答诚实说明至少一个材料取舍；
- 最后只推动一个清晰的下一步问题。

再测试：

```text
脚感最重要
卧室
预算偏高
北欧原木
```

预期主推方向应更偏向多层实木或三层实木，并说明预算、防潮维护或宠物适配方面的取舍。

## 本阶段未实现

以下内容属于后续阶段：

- 真实促销活动与有效期校验；
- 库存和报价系统；
- 联系方式授权表单；
- 营销信息单独授权；
- CRM 销售工作台和跟进提醒。

这些信息在接入真实数据前，不允许由 LLM 自行生成。
