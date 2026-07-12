# 高级销售顾问 Phase 1

本阶段把原来的“需求登记 + 推荐”流程升级为受 Backend 控制的高级销售顾问流程。

## 已实现能力

- 新客户开场介绍顾问角色、门店定位、服务方法和特色方案；
- 第一项发现问题从“哪个房间”改为“最不愿意妥协的核心需求”；
- Backend 保存 `primary_purchase_driver`，并把它作为推荐解释中心；
- 确定性的 `SalesConversationPolicy` 计算销售阶段、目标和下一最佳动作；
- 推荐结果区分“主推款”和“备选款”；
- Terra 与 Qwen 都必须说明实际价值和至少一个诚实取舍；
- LLM 只能使用 Backend 批准的公司、系列和产品信息。

## 模拟数据

```text
backend/app/data/company_profile.json
backend/app/data/product_collections.json
```

替换真实资料时，保留现有 JSON 字段结构即可，不需要重新设计对话编排。

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

## Phase 1 离线静态检查

不需要 OpenAI API Key，也不需要启动 Ollama：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_senior_sales.ps1
```

脚本默认通过：

```text
conda run --no-capture-output -n smartoffice
```

执行，因此不依赖当前 PowerShell 是否执行过 `conda init`，也不会意外使用 base Python。

环境名称不是 `smartoffice` 时：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_senior_sales.ps1 `
  -CondaEnvironment your-environment-name
```

也可以明确指定解释器：

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_senior_sales.ps1 `
  -PythonExecutable "D:\anaconda3\envs\smartoffice\python.exe"
```

成功时应看到：

```text
Senior sales phase-one static check passed.
```

## 推荐人工测试流程

新建 Session 后依次回答：

```text
耐磨最重要
客厅
预算中等
现代简约
```

预期：

- 系统保存“耐磨”为首要购买驱动；
- 信息足够后自动推荐；
- 明确说出主推款和备选款；
- 解释耐磨、空间与预算的关系；
- 诚实说明材料取舍；
- 只推动一个清晰的下一步问题。

脚感型测试：

```text
脚感最重要
卧室
预算偏高
北欧原木
```

预期主推方向偏向多层实木或三层实木，并说明预算、防潮维护或宠物适配方面的取舍。

## 后续阶段状态

Phase 2 和 Phase 3 已经实现，不再属于待办项，包括：

- 受控模拟促销及有效期、产品、房间和面积校验；
- 项目面积与铺装时间资格确认；
- 异议处理、lead temperature 和 soft close；
- 联系方式独立表单；
- 本次方案联系与长期营销分开授权；
- 本地 CRM、跟进状态和三天提醒；
- 客户撤回授权与永久删除；
- 门店销售工作台。

完整说明见：

```text
backend/SALES_PHASE2_3.md
```

真实促销、报价、库存、质保和认证数据仍需由业务方提供和审核；在此之前，LLM 不得自行生成这些信息。
