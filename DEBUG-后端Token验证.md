# 后端Token验证诊断指南

## 快速测试步骤

### 1. 打开后端日志监控

在终端运行（保持窗口开启）：

```bash
docker logs -f hr-agent-api-1 2>&1 | grep -E "\[薪资Token验证\]|\[get_current_user\]|\[Planner\]"
```

### 2. 清除浏览器缓存

在浏览器控制台（F12）运行：

```javascript
localStorage.clear();
location.reload();
```

### 3. 重新登录

- 用户名：`biz_hrd`
- 密码：（你的测试密码）

### 4. 提问薪资问题

在智能体输入框输入：

```
我的工资是多少
```

### 5. 观察现象

#### 预期正常流程：

1. **首次问**：前端弹出二次确认窗口
2. **填写事由并确认**：
   - 后端日志出现：`[薪资Token验证] ✅ 验证通过!`
   - 后端日志出现：`[Planner] ✅ 分支: 业务超管已确认 -> 放行查询`
   - 前端收到答案（不再弹窗）
3. **30分钟内再问**：
   - 前端不再弹窗
   - 后端日志显示 token 复用
   - 直接返回答案

#### 异常流程（仍然循环）：

后端日志会显示具体原因：

- `[薪资Token验证] ❌ token为空` → 前端未发送 header
- `[薪资Token验证] ❌ token不存在于内存` → 后端重启或 token 已过期
- `[Planner] ⚠️ 分支: 业务超管但未确认` → Token 验证失败

## 关键日志解读

### A. 正常流程日志示例

```
# 第1次请求（未确认）
[get_current_user] X-Payroll-Confirm header: None...
[薪资Token验证] username=biz_hrd, token=None...
[薪资Token验证] ❌ token为空
[get_current_user] username=biz_hrd, role=biz_super_admin, confirmed=False
[Planner] role=biz_super_admin, payroll_access=True, payroll_confirmed=False
[Planner] ⚠️  分支: 业务超管但未确认 -> 要求二次确认

# 用户确认后的第2次请求（带token）
[get_current_user] X-Payroll-Confirm header: HL12iIAB...
[薪资Token验证] username=biz_hrd, token=HL12iIAB...
[薪资Token验证] ✅ 验证通过! expires_at=1748440215, now=1748438415
[get_current_user] username=biz_hrd, role=biz_super_admin, confirmed=True
[Planner] role=biz_super_admin, payroll_access=True, payroll_confirmed=True
[Planner] ✅ 分支: 业务超管已确认 -> 放行查询
```

### B. 异常流程日志示例（循环）

```
# 每次都要求确认（token 验证失败）
[get_current_user] X-Payroll-Confirm header: HL12iIAB...
[薪资Token验证] username=biz_hrd, token=HL12iIAB...
[薪资Token验证] ❌ token不存在于内存（可能已过期或未生成）
[薪资Token验证] 当前内存中的tokens: ['qLR9L8Hw...']  # 不匹配
[get_current_user] username=biz_hrd, role=biz_super_admin, confirmed=False
[Planner] ⚠️  分支: 业务超管但未确认 -> 要求二次确认
```

## 问题定位

根据日志判断问题类型：

| 日志现象 | 问题定位 | 解决方向 |
|---------|---------|---------|
| `X-Payroll-Confirm header: None` | 前端未发送 token | 检查前端 `apiHeaders()` |
| `token不存在于内存` + token 每次都不同 | 前端每次生成新 token | 检查前端 TTL 逻辑 |
| `token不存在于内存` + token 相同 | 后端重启或过期 | 检查后端是否重启、TTL 设置 |
| `username不匹配` | JWT 与 token 不一致 | 罕见，检查登录流程 |
| `confirmed=True` 但仍要求确认 | Planner 逻辑错误 | 检查 planner.py 分支 |

## 常见问题

### Q1: 后端日志没有输出

**原因**：日志可能被其他输出淹没  
**解决**：使用更精确的 grep：

```bash
docker logs -f hr-agent-api-1 2>&1 | grep --line-buffered -E "薪资Token|Planner.*分支"
```

### Q2: Token 验证通过但仍要求确认

**原因**：`confirmed=True` 传给了 planner，但 planner 的 `payroll_confirmed` 仍为 `False`  
**检查**：
1. 后端日志：`[get_current_user] confirmed=True`
2. 后端日志：`[Planner] payroll_confirmed=True`
3. 如果两者不一致，检查 `agent.py` 的 `run_agent_stream()` 是否正确传递

### Q3: Token 每次都不同

**原因**：前端每次都调用 `/api/v1/admin/payroll/confirm` 生成新 token  
**检查**：
1. 前端控制台：`localStorage.getItem('payrollConfirmedUntil')`
2. 如果为空或已过期，检查前端 `submitPayrollConfirm()` 是否正确设置
3. 如果 TTL 内仍生成新 token，检查 `ensurePayrollAccess()` 的 TTL 判断逻辑

---

**修改时间**: 2026-05-28 18:30  
**相关文档**: `docs/FIX-后端Token验证-2026-05-28.md`
