# 高级销售顾问 Phase 2 与 Phase 3

本文说明 Demo 中新增的促销、异议处理、销售推进、联系方式授权和本地 CRM 功能。

## 数据声明

当前公司、产品线和促销活动均为模拟数据。促销数据文件：

```text
backend/app/data/promotions.json
```

所有促销都必须：

- 标记为演示活动；
- 在有效日期内；
- 匹配指定产品或特色系列；
- 满足房间和面积条件；
- 使用 Backend 批准的话术；
- 明确最终权益和报价由门店书面确认。

LLM 无权自行创造折扣、库存紧张、赠品、原价、质保或截止日期。

---

# Phase 2：受控销售推进

## 新增能力

### 项目资格确认

在首次形成产品推荐后，系统会继续确认：

```text
预计铺装面积
计划铺装时间
项目类型与决策阶段（客户主动提及时）
```

面积和时间用于：

- 判断模拟促销是否适用；
- 确定跟进优先级；
- 为后续正式报价和安装安排准备信息。

### 促销判断

核心实现：

```text
backend/app/services/promotion_service.py
```

判断链路：

```text
当前日期有效
+ 活动 active
+ 推荐产品匹配
+ 特色系列匹配
+ 房间条件匹配
+ 面积条件通过或需要补充面积
→ 才能进入 AnswerPlan
→ Terra/Qwen 只能复述 approved_message
```

客户接口：

```text
GET /api/promotions/active
GET /api/sales/catalog
```

### 异议处理

系统确定性识别以下顾虑：

```text
价格顾虑
需要比较
需要与家人商量
防水顾虑
环保顾虑
维护顾虑
脚感顾虑
颜色顾虑
```

异议不会永久锁死后续对话。历史顾虑保留在客户摘要中，但只有客户当前轮再次表达顾虑或追问原因时，才进入 `objection_handling` 阶段。

### Lead temperature

Backend 根据已确认需求、推荐结果、面积、时间、决策阶段、促销兴趣和顾虑，计算：

```text
cold
warm
hot
```

该结果只用于决定下一最佳销售动作，不代表真实成交概率。

### Soft close

客户已获得推荐后，系统会推动一个低压力下一步，例如：

- 确认面积；
- 确认铺装时间；
- 核对样板；
- 核对正式报价；
- 自愿获取本次方案。

系统不得制造虚假紧迫感。

---

# Phase 3：联系方式授权与本地 CRM

## 双重授权

联系方式页面：

```text
http://127.0.0.1:5173/follow-up.html
```

主界面右下角也提供：

```text
获取方案与后续联系
```

授权被严格拆分为：

```text
1. 本次方案联系授权（必选）
   用于发送本次方案、报价、样板或预约安排

2. 新品与优惠信息授权（可选）
   用于后续营销信息
```

未勾选第二项，不影响获取本次方案。

## PII 隔离

真实联系方式只保存于本地 SQLite CRM 表：

```text
sales_leads
lead_consent_events
lead_follow_up_events
```

Terra 和 Qwen 看不到：

```text
姓名
手机号
微信号
邮箱
contact_value
```

LLM 只能看到：

```text
contact_opt_in
marketing_opt_in
contact_prompt_eligible
```

这些布尔状态用于避免重复索取联系方式。

## CRM API

```text
POST   /api/leads/contact
GET    /api/leads/contact/status?session_id=...
PATCH  /api/leads/contact/consent
DELETE /api/leads/contact

GET    /api/crm/status
GET    /api/crm/leads
GET    /api/crm/reminders/due
POST   /api/crm/leads/follow-up
```

### 保存联系方式示例

```powershell
$body = @{
  session_id = "session-replace-with-real-id"
  display_name = "王先生"
  contact_channel = "phone"
  contact_value = "+61412345678"
  contact_opt_in = $true
  marketing_opt_in = $false
  contact_purposes = @(
    "发送本次选购方案",
    "跟进报价与样板"
  )
  preferred_contact_time = "工作日下午 3 点后"
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/leads/contact" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body $body |
ConvertTo-Json -Depth 20
```

### 撤回营销授权，保留本次方案联系

```powershell
$body = @{
  session_id = "session-replace-with-real-id"
  contact_opt_in = $true
  marketing_opt_in = $false
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/leads/contact/consent" `
  -Method Patch `
  -ContentType "application/json; charset=utf-8" `
  -Body $body |
ConvertTo-Json -Depth 20
```

### 撤回全部主动联系授权

```powershell
$body = @{
  session_id = "session-replace-with-real-id"
  contact_opt_in = $false
  marketing_opt_in = $false
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/leads/contact/consent" `
  -Method Patch `
  -ContentType "application/json; charset=utf-8" `
  -Body $body |
ConvertTo-Json -Depth 20
```

## 三天跟进提醒

客户授权本次方案联系后，系统默认生成：

```text
next_follow_up_at = 授权时间 + 3 天
```

它只是本地提醒，不会自动发送短信、微信或邮件。

查看到期提醒：

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/crm/reminders/due" `
  -Method Get |
ConvertTo-Json -Depth 30
```

## 门店销售工作台

```text
http://127.0.0.1:5173/crm-workbench.html
```

支持：

- 全部有效线索；
- 到期提醒；
- cold / warm / hot；
- 联系和营销授权状态；
- 脱敏或本机完整联系方式；
- 已介绍的演示活动；
- 更新跟进状态；
- 跟进备注；
- 设置下一次跟进时间。

当前工作台没有账号登录和权限控制，只能用于本机 Demo，不得暴露到公网。

生产化前必须增加：

```text
身份认证
角色权限
HTTPS
数据库加密
访问审计
数据保留与自动清理策略
CRM 导出/同步审批
```

## 数据删除

客户可以：

- 只撤回营销授权；
- 撤回全部联系授权；
- 永久删除联系方式及跟进记录；
- 通过“隐私与数据”删除人脸、客户身份、CRM 联系记录和关联历史。

回访客户的新 Session 不会自动继承上次 Session 的联系或营销授权。

---

# 合并离线检查

不需要启动 Ollama、Terra、摄像头或 Backend：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_sales_phase2_3.ps1
```

脚本默认通过：

```text
conda run -n smartoffice
```

执行，避免子 PowerShell 错误使用 base Python。

成功时应看到：

```text
Sales phase-two/three static check passed.
Contact PII excluded from LLM prompt: yes
Separate contact and marketing consent: yes
Three-day local follow-up reminder: yes
Consent revocation and permanent CRM deletion: yes
```
