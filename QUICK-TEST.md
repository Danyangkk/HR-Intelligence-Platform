# 快速测试 - 薪资确认问题

## ⚠️ 重要：清除缓存

### 方法1：强制刷新（推荐）
```
Mac: Cmd + Shift + R
Windows: Ctrl + Shift + R
```

### 方法2：清除缓存
1. 打开浏览器
2. 按 `Cmd + Shift + Delete` (Mac) 或 `Ctrl + Shift + Delete` (Windows)
3. 选择"缓存的图片和文件"
4. 时间范围选"全部"
5. 点击"清除数据"
6. **关闭浏览器，重新打开**

---

## 🧪 测试步骤

### 第一步：验证调试代码已加载

1. 打开 http://localhost:8080
2. 按 **F12** 打开控制台
3. 在控制台输入以下代码并按回车：

```javascript
console.log('测试1: submitPayrollConfirm函数', typeof submitPayrollConfirm);
console.log('测试2: handlePayrollConfirmForAgent函数', typeof handlePayrollConfirmForAgent);
console.log('测试3: apiHeaders函数', typeof apiHeaders);
```

**预期输出**：
```
测试1: submitPayrollConfirm函数 function
测试2: handlePayrollConfirmForAgent函数 function  
测试3: apiHeaders函数 function
```

**如果输出 `undefined`**：说明代码还没加载，请重新执行"清除缓存"步骤。

---

### 第二步：验证调试日志

1. 在控制台输入：

```javascript
// 临时覆盖console.log来测试
const oldLog = console.log;
console.log = function(...args) {
  oldLog.apply(console, ['✓', ...args]);
};
console.log('调试日志已启用');
```

2. 然后测试薪资查询流程

---

### 第三步：手动触发薪资确认

如果上面都正常，在控制台直接测试确认流程：

```javascript
// 1. 登录
await authLogin('biz_hrd', 'hrd123');

// 2. 检查AUTH对象
console.log('AUTH对象:', {
  role: AUTH.role,
  token: AUTH.token ? '有' : '无',
  payrollConfirmToken: AUTH.payrollConfirmToken || '无'
});

// 3. 手动调用确认（模拟弹窗提交）
// 注意：需要先打开智能体并触发一次薪资查询让弹窗出现
```

---

## 🔍 诊断检查清单

在控制台运行：

```javascript
// 完整诊断
console.log('=== 诊断报告 ===');
console.log('1. AUTH对象:', AUTH);
console.log('2. 全局函数检查:', {
  submitPayrollConfirm: typeof submitPayrollConfirm,
  handlePayrollConfirmForAgent: typeof handlePayrollConfirmForAgent,
  ensurePayrollAccess: typeof ensurePayrollAccess,
  openPayrollConfirmModal: typeof openPayrollConfirmModal,
  apiHeaders: typeof apiHeaders
});
console.log('3. DOM元素检查:', {
  弹窗: document.getElementById('payrollConfirmModal') ? '存在' : '不存在',
  输入框: document.getElementById('payrollConfirmReason') ? '存在' : '不存在'
});
```

---

## 📝 报告问题

如果测试失败，请提供以下信息：

1. **第一步的输出**（函数类型检查）
2. **完整诊断报告的输出**
3. **浏览器版本**（在地址栏输入 `chrome://version/` 或 `about:support`）
4. **是否使用了隐私模式/无痕模式**

---

## 💡 已知问题

### 问题：控制台一片空白
**原因**：浏览器缓存了旧版本的JS文件

**解决**：
1. **完全关闭浏览器**（不是只关标签页）
2. 清除浏览器缓存
3. 重新打开浏览器
4. 访问 http://localhost:8080

### 问题：函数显示 undefined
**原因**：新代码还没加载

**解决**：
1. 检查 Network 标签
2. 找到 `permission-admin.js?v=1779963244`
3. 查看是否返回 200
4. 查看文件内容是否包含 `[薪资确认]` 等调试日志

---

## 🚀 最终测试（确保一切正常）

```javascript
// 在控制台运行完整测试
(async function() {
  console.log('开始完整测试...');
  
  // 1. 登录
  try {
    await authLogin('biz_hrd', 'hrd123');
    console.log('✓ 登录成功');
  } catch(e) {
    console.error('✗ 登录失败:', e);
    return;
  }
  
  // 2. 检查角色
  if(AUTH.role !== 'biz_super_admin') {
    console.error('✗ 角色错误，当前:', AUTH.role);
    return;
  }
  console.log('✓ 角色正确: biz_super_admin');
  
  // 3. 测试API headers
  const headers = apiHeaders();
  console.log('✓ API Headers:', headers);
  
  // 4. 测试确认token API
  try {
    const result = await apiPost('/admin/payroll/confirm-access', {
      target_ref: '测试',
      entry: '智能体',
      fields: '薪资',
      reason: '测试用途'
    });
    console.log('✓ 确认API成功:', result);
    console.log('✓ Token:', result.confirm_token);
  } catch(e) {
    console.error('✗ 确认API失败:', e);
  }
  
  console.log('测试完成！');
})();
```

如果这个测试通过，说明基础功能正常，问题可能在具体的交互流程中。
