# Sales Phase 2 + 3

高级销售顾问第二、第三阶段已经实现。

完整架构、API、隐私规则、联系方式授权、CRM 工作台和测试命令见：

```text
backend/SALES_PHASE2_3.md
```

主要页面：

```text
客户获取方案与授权：
http://127.0.0.1:5173/follow-up.html

门店本地 CRM 工作台：
http://127.0.0.1:5173/crm-workbench.html

客户隐私与数据删除：
http://127.0.0.1:5173/delete-my-data.html
```

离线合并检查：

```powershell
cd F:\emergency-wood-floor-greeter-demo\backend

powershell -ExecutionPolicy Bypass `
  -File .\scripts\smoke_test_sales_phase2_3.ps1
```

当前公司、产品系列和促销内容均为明确标记的模拟 Demo 数据。接入真实业务前必须替换并由门店负责人审核。
