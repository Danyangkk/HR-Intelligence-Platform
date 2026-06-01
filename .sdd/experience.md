# HR-Agent 项目经验

> 当前项目长期有效的经验。  
> Developer / Tester / Bugfix 在任务完成后维护本文件。

---

## Harness 系统经验摘要

新项目开始时，Developer / Tester / Bugfix 需要同时参考：

- 当前项目经验：`.sdd/experience.md`
- 系统级经验：`<SDD_V6>/memory/harness-experience.md`

---

## 前端缓存管理（Bugfix BUG-001）

**问题**: 重大功能修复后用户浏览器仍运行旧代码

**场景**: 2026-05-28，业务超管薪资弹窗修复后，用户普通刷新无法加载新代码

**解决方案**:
1. ⚠️ **代码修复后必须通知用户强制刷新**（Mac: Cmd + Shift + R，Windows: Ctrl + Shift + R）
2. 📝 **HTML中JS引用添加版本号参数**（`?v=timestamp`）
3. 🔧 **开发环境nginx配置短期缓存**（HTML: 5分钟，JS/CSS: 10分钟）
4. 🚀 **生产环境使用构建工具生成文件名hash**（webpack/vite）

**注意事项**:
- nginx的`Cache-Control`对浏览器强缓存影响有限，关键是用户操作
- 版本号参数`?v=`有效，但首次缓存后需强制刷新才能更新
- 开发者工具Network面板的"Disable cache"仅对当前会话有效

**相关文件**:
- `nginx/nginx.conf` - 开发环境缓存策略
- `nginx/nginx.conf.production` - 生产环境推荐配置
- `docs/生产环境部署指南-缓存策略.md` - 部署文档

---

## 薪资功能安全合规（前端页面规格）

**规范要求**:
- ✅ 业务超管访问薪资数据**必须二次确认**
- ✅ 二次确认**必须填写访问事由**并审计留痕
- ✅ 非业务超管直接拦截并Toast提示
- ✅ 薪资分类对非业务超管**置灰+锁图标**（不是隐藏）

**实现位置**:
- `frontend/permission-admin.js` - `ensurePayrollAccess()`, `openPayrollConfirmModal()`, `filterCategoryTree()`
- `frontend/index.html` - `selectL2()`, `selectL3()`, `handleAgentEvent()`, `renderTree()`
- `backend/src/agent/planner.py` - 薪资查询拦截逻辑（reject_reason = "需要二次确认"）

**关键点**:
- `openPayrollConfirmModal` 必须暴露到 `global` 以便跨模块调用
- 智能体薪资查询需检测 `reject` 事件的 `data.reason === '需要二次确认'`
- 薪资分类只对业务超管可访问，其他角色置灰（`disabled: true`）

**相关文档**:
- `/Users/kk/Downloads/前端页面规格-权限重构 (1).md` - 产品规格SSOT
- `docs/薪资二次确认修复完成-2026-05-28.md` - 初次修复报告
- `docs/BUGFIX-薪资弹窗-2026-05-28.md` - 缓存问题修复报告（BUG-001）
- `docs/BUGFIX-薪资弹窗触发位置-2026-05-28.md` - 触发位置修复报告（BUG-002）

---

## 薪资二次确认触发逻辑（规格粒度B）（Bugfix BUG-002）

**问题**: 薪资二次确认弹窗触发点绑错位置——"首次进入薪资区"没弹，"切 Tab"才弹

**规格要求**（粒度B）:
- ✅ **触发粒度**: 业务超管本会话**首次访问薪资区**时弹一次确认
- ✅ **会话内不再弹**: 本会话内所有薪资数据请求（切表/翻页/筛选/换L2薪资子类）都不再弹
- ✅ **登出重置**: 重新登录后，首次访问薪资再次弹窗

**实现要点**:
1. **会话标记**: `AUTH.payrollConfirmedThisSession`（布尔值）
2. **触发收口**: 所有会加载薪资数据的路径都调用统一的`ensurePayrollAccess`
   - 点击L2薪资分类（`selectL2`）→ 自动加载第一张L3表前检查
   - 切换L3 Tab（`selectL3`）→ 加载前检查
   - 智能体薪资查询（`handleAgentEvent`）→ 生成答案前检查
3. **登出重置**: `authLogout`函数中重置会话标记

**错误案例**:
- ❌ **只在L3 Tab切换时检查**: 会导致"点L2进入薪资区"无弹窗
- ❌ **使用单次token而非会话标记**: 会导致每次请求都弹窗，不符合粒度B

**正确路径**:
```
点L2薪资分类 → selectL2 检查第一张L3 → ensurePayrollAccess
切L3 Tab → selectL3 → ensurePayrollAccess
智能体薪资查询 → reject"需要二次确认" → handlePayrollConfirmForAgent → ensurePayrollAccess
```

**验证要点**:
- 点L2薪资分类进入 → 立即弹窗 ✅
- 本会话内切换L3 Tab → 不弹窗 ✅
- 本会话内切换到其他L2薪资分类 → 不弹窗 ✅
- 登出重新登录 → 再次首访薪资弹窗 ✅

**相关文件**:
- `frontend/index.html` - `AUTH.payrollConfirmedUntil`, `selectL2()`, `selectL3()`
- `frontend/permission-admin.js` - `ensurePayrollAccess()`, `authLogout()`

---

## 薪资确认30分钟TTL（账号级，两入口共用）（Feature 2026-05-28）

**问题**: 会话级确认导致刷新页面需要重新弹窗，数据中台和智能体不共用确认状态

**新方案**:
- ✅ **30分钟TTL**: 确认后30分钟内访问薪资无需重新确认
- ✅ **两入口共用**: 数据中台确认后，智能体也在TTL内免弹；反之亦然
- ✅ **登出重置**: 登出后TTL失效，重新登录需重新确认

**实现要点**:
1. **时间戳TTL**: `AUTH.payrollConfirmedUntil = Date.now() + 30 * 60 * 1000`
2. **检查逻辑**: `Date.now() < AUTH.payrollConfirmedUntil` → 免弹，否则弹窗
3. **事由复用**: `AUTH.payrollConfirmReason` 存储TTL期内复用的事由
4. **登出重置**: `authLogout` 中重置 `payrollConfirmedUntil = 0`

**TTL行为**:
```
数据中台确认 → 30分钟内智能体查薪资免弹 ✅
智能体确认 → 30分钟内数据中台查薪资免弹 ✅
确认后刷新页面 → 30分钟内免弹 ✅
31分钟后再访问 → 重新弹窗 ✅
登出重新登录 → 重新弹窗 ✅
```

**相关文件**:
- `frontend/index.html` - `AUTH.payrollConfirmedUntil`, `AUTH.payrollConfirmReason`
- `frontend/permission-admin.js` - `ensurePayrollAccess()` 检查TTL

---

## 薪资访问审计表字段规范（合规要求）（Feature 2026-05-28）

**问题**: 
1. 访问人显示角色代码（`biz_hrd`），无法追溯到具体人
2. 智能体查询未记录被查员工，只写"个人薪资明细"
3. 数据中台"访问对象"和"字段"重复（都写"工资"）

**正确填写规范**:
| 字段 | 数据中台入口 | 智能体入口 |
|------|-------------|-----------|
| 访问人 | 张HRD（HR0001） | 张HRD（HR0001） |
| 访问对象 | 表名（月度工资表） | 被查员工（张三 A0123） |
| 入口 | 数据中台 | 智能体 |
| 字段 | 薪资 | 奖金/工资 |
| 事由 | 用户填的 | 用户填的 |

**实现要点**:
1. **访问人格式化**: `f"{actor_display}（{employee_id}）"` - 后端自动格式化
2. **访问对象区分**: 
   - 数据中台: `target_ref = l3Name(id)`（表名）
   - 智能体: `target_ref = "被查员工（工号）"`（需实现）
3. **入口明确**: 前端传递 `entry="数据中台"` 或 `entry="智能体"`
4. **字段准确**: 前端传递 `fields="薪资"` 或具体字段，不要和对象重复

**红线**: 
- ❌ 永不记录薪资数值本身
- ❌ 不要记录角色代码（如`biz_hrd`），要记录具体人
- ❌ 智能体查询必须记录被查员工，不能写"个人薪资明细"

**相关文件**:
- `backend/src/services/payroll_access.py` - `log_payroll_access()` 格式化
- `frontend/index.html` - `selectL2()`, `selectL3()` 传递正确参数
- `frontend/permission-admin.js` - `submitPayrollConfirm()` 使用上下文fields
