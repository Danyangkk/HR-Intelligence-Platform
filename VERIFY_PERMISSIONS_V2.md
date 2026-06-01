# 权限重构 V2 - 快速验证指南

## 快速启动

### 1. 运行迁移（清理旧数据，应用新模型）

```bash
cd /Users/kk/Desktop/HR-Agent/backend
alembic upgrade head
```

### 2. 重新 seed 演示用户

```bash
cd /Users/kk/Desktop/HR-Agent/backend
python -m src.seed.run
```

### 3. 启动后端

```bash
cd /Users/kk/Desktop/HR-Agent/backend
PYTHONPATH=.. python3.11 -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. 打开前端

浏览器访问：`http://localhost:8080`

---

## 验证场景

### 场景 1: 技术超管（永久无薪资权）

**登录**：`tech_admin` / `tech123`

✅ **预期行为**：
- 左侧导览：**薪资分类隐藏**（看不到"薪酬"）
- 系统管理：显示"用户管理"按钮，**无"薪资发证"**
- 薪资审计：可见（但只看元数据，无金额）
- 我的工单：可见并可操作
- 复盘报告：可见
- 改进工单：可见并可操作

🧪 **测试**：
1. 在超级智能体问："李C&B的工资是多少？"
   - **预期**：被拒绝，提示"涉及个人薪资明细"
2. 尝试访问 `http://localhost:8080` 后切换到数据中台
   - **预期**：左侧树无"薪酬"分类

---

### 场景 2: 业务超管（岗位自带薪资权）

**登录**：`biz_hrd` / `hrd123`

✅ **预期行为**：
- 左侧导览：**薪资分类显示**（"薪酬"可见）
- 系统管理：**无"用户管理"**、**无"薪资发证"**
- 薪资审计：可见
- 复盘报告：可见
- 改进工单：可见，待处理工单有"编辑""撤回"按钮
- 我的工单：**不可见**（非技术超管）

🧪 **测试**：
1. 切换到数据中台 → 点击"薪酬"分类 → 选择"月度工资表"
   - **预期**：弹出"薪资数据访问确认"，填事由后才显示
2. 在超级智能体问："李C&B的工资是多少？"
   - **预期**：弹出"薪资数据访问确认"，填事由后才回答
3. 切换到系统管理 → 薪资审计
   - **预期**：可看到自己的访问记录

---

### 场景 3: 普通员工（永久薪资隔离）

**登录**：`staff1` / `staff123`

✅ **预期行为**：
- 左侧导览：**薪资分类隐藏**
- 系统管理：**不显示**（无任何管理权限）
- 数据中台：可增删改导入，但薪资字段脱敏（显示 `***`）

🧪 **测试**：
1. 在超级智能体问："我的工资是多少？"
   - **预期**：被拒绝，提示"涉及个人薪资明细"
2. 切换到数据中台 → 选择非薪资表（如"员工花名册"）
   - **预期**：可正常查看，但身份证号等敏感字段脱敏

---

## 关键变更确认

### ✅ 用户管理页

- **无"薪资权限"列**（从 6 列减为 5 列）
- 业务超管显示 `[🔑薪资]` 徽章
- 说明文本："薪资访问权随业务超管角色自带，不单独授予"

### ✅ 系统管理导航

- **无"薪资发证"按钮**（技术超管、业务超管都看不到）
- 顺序：用户管理 → 薪资审计 → 复盘报告 → 改进工单 → 我的工单

### ✅ 复盘报告页

- 显示量化概览（总问答、👎率、超时率、RAG0命中）
- 显示问题归类与归因
- 显示改进建议（可采纳→生成工单）
- 说明文本："复盘仅基于运行元数据（全量聚合），不含薪资数值、不暴露任何个人逐条问答原文"

### ✅ 改进工单页

- 业务超管对待处理工单有"编辑""撤回"按钮（mock 实现）
- 业务超管对处理中工单有"加备注"按钮（mock 实现）
- 技术超管在"我的工单"可接单、标记完成、确认上线

### ✅ 登录提示

更新为：
```
演示账号：
tech_admin/tech123（技术超管，永久无薪资权）
· biz_hrd/hrd123（业务超管[🔑]，岗位自带薪资权）
· staff1/staff123（普通员工，永久薪资隔离）
```

---

## 故障排查

### 问题：迁移失败

```bash
# 查看当前迁移版本
cd backend
alembic current

# 如果卡在旧版本，强制升级
alembic upgrade head --sql  # 先看 SQL
alembic upgrade head        # 执行
```

### 问题：seed 用户失败

```bash
# 手动清理
psql -d hr_agent -c "DELETE FROM users WHERE username IN ('sys_admin');"

# 重新 seed
python -m src.seed.run
```

### 问题：前端薪资分类仍显示

1. 确认已迁移到 008
2. 确认已重新 seed 用户
3. 清除浏览器 localStorage：
   ```javascript
   // 浏览器控制台
   localStorage.clear();
   location.reload();
   ```
4. 重新登录

### 问题：二次确认弹窗不弹

1. 确认登录的是 `biz_hrd`（业务超管）
2. 确认 `permission-admin.js` 已更新
3. 检查浏览器控制台是否有 JS 错误
4. 强制刷新（Cmd+Shift+R / Ctrl+Shift+F5）

---

## API 验证（可选）

### 测试技术超管访问薪资表（应被拒）

```bash
# 1. 登录获取 token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"tech_admin","password":"tech123"}' \
  | jq -r '.data.access_token')

# 2. 尝试访问薪资表
curl -X GET "http://localhost:8000/api/v1/data/l3-4-1-1?page=1" \
  -H "Authorization: Bearer $TOKEN"

# 预期：403 Forbidden
```

### 测试业务超管访问薪资表（需二次确认）

```bash
# 1. 登录
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"biz_hrd","password":"hrd123"}' \
  | jq -r '.data.access_token')

# 2. 先确认（获取 confirm_token）
CONFIRM=$(curl -s -X POST http://localhost:8000/api/v1/admin/payroll/confirm-access \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_ref":"API测试","entry":"数据中台","fields":"月度工资表","reason":"核算调薪"}' \
  | jq -r '.data.confirm_token')

# 3. 带 confirm_token 访问薪资表
curl -X GET "http://localhost:8000/api/v1/data/l3-4-1-1?page=1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Payroll-Confirm: $CONFIRM"

# 预期：200 OK，返回薪资数据
```

---

## 完成确认

权限重构 V2 验证完成后，请在此打勾：

- [ ] 技术超管永久无薪资权 ✅
- [ ] 业务超管岗位自带薪资权，访问需二次确认 ✅
- [ ] 普通员工永久薪资隔离 ✅
- [ ] 用户管理页无薪资权限列 ✅
- [ ] 系统管理无薪资发证按钮 ✅
- [ ] 复盘报告页展示量化概览 ✅
- [ ] 改进工单页业务超管可编辑待处理 ✅
- [ ] 迁移成功，sys_admin 已删除 ✅
- [ ] 所有 RBAC 测试通过 ✅

---

**文档版本**：V2  
**最后更新**：2026-05-28  
**规格参考**：`前端页面规格-权限重构 (1).md`
