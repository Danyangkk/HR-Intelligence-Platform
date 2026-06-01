# 调试：薪资确认问题

## 问题描述
填完薪资确认表格后仍然不停报错，无法继续智能体查询。

## 调试步骤

### 1. 强制刷新浏览器
```
Windows: Ctrl + Shift + R
Mac: Cmd + Shift + R
```

### 2. 打开浏览器开发者工具
```
按 F12 或右键页面 > 检查
点击 "Console" 标签
```

### 3. 测试薪资查询
```
1. 登录：biz_hrd / hrd123
2. 点击"超级智能体"
3. 输入："张三的工资是多少？"
4. 弹窗出现后，填写事由
5. 点击"确认并查看"
```

### 4. 查看控制台输出

应该会看到类似以下的调试日志：

```javascript
[薪资确认] 提交确认，上下文: {target_ref: "个人薪资查询", entry: "智能体", fields: "薪资"}
[薪资确认] 后端返回: {confirm_token: "xxx..."}
[薪资确认] Token已保存: xxx...
[智能体薪资] 确认结果: true | Token: xxx...
[智能体薪资] 确认成功，重新发送请求
[API请求] 添加薪资确认头: xxx...
```

### 5. 如果看到错误

请截图或复制以下信息：
- 控制台中的所有红色错误信息
- 调试日志中的输出
- 网络请求的详细信息（Network标签）

## 可能的问题

### 问题1：Token未保存
**现象**: 看到 `[薪资确认] Token已保存: undefined`

**原因**: 后端返回的数据格式不对

**解决**: 需要检查后端API返回

### 问题2：Token未传递
**现象**: 没有看到 `[API请求] 添加薪资确认头` 日志

**原因**: apiHeaders函数没有执行

**解决**: 检查AUTH对象状态

### 问题3：后端拒绝请求
**现象**: 看到错误信息 "需要二次确认" 或 "薪资数据需二次确认后访问"

**原因**: 后端没有接收到token或token验证失败

**解决**: 检查X-Payroll-Confirm头是否正确传递

## 后端日志查看

如需查看后端日志：

```bash
cd /Users/kk/Desktop/HR-Agent
docker compose logs api --tail=100 --follow
```

关注以下信息：
- token验证相关日志
- planner拒绝原因
- 权限检查结果

## 快速测试Token

在浏览器控制台输入以下代码：

```javascript
// 1. 检查Token是否存在
console.log('Token:', AUTH.payrollConfirmToken);

// 2. 检查TTL
console.log('TTL:', AUTH.payrollConfirmedUntil, 'Now:', Date.now());

// 3. 手动测试API请求头
console.log('Headers:', apiHeaders());

// 4. 测试token验证端点
fetch('/api/v1/admin/payroll/validate-token', {
  headers: apiHeaders()
}).then(r => r.json()).then(console.log);
```

## 预期的正常流程

1. 用户点击"确认并查看"
2. 前端调用 `/admin/payroll/confirm-access`
3. 后端返回 `confirm_token`
4. 前端保存到 `AUTH.payrollConfirmToken`
5. 前端重新发送智能体请求
6. `apiHeaders()` 自动添加 `X-Payroll-Confirm: <token>`
7. 后端验证token，设置 `payroll_confirmed = True`
8. Planner检查 `payroll_confirmed`，不再reject
9. Agent正常返回薪资数据

## 联系开发

如果以上步骤无法解决问题，请提供：
1. 浏览器控制台的完整截图
2. 具体的错误信息
3. 测试时的用户名和操作步骤
