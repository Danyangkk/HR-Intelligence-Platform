# 清除缓存并重新测试的步骤

## 🔄 请按以下步骤操作：

### 1. 打开浏览器开发者工具
- Mac: `Cmd + Option + I`
- Windows: `F12`

### 2. 清除缓存和localStorage
在Console控制台输入以下命令：

```javascript
// 清除所有localStorage
localStorage.clear();

// 清空AUTH对象
if(window.AUTH) {
  AUTH.token = '';
  AUTH.role = '';
  AUTH.payrollAccess = false;
}

// 打印当前状态验证
console.log('清除完成');
```

### 3. 强制刷新页面
- Mac: `Cmd + Shift + R`
- Windows: `Ctrl + Shift + R`

或者在Network面板勾选"Disable cache"后刷新

### 4. 重新登录
使用业务超管账号：
- 用户名: `biz_hrd`
- 密码: `hrd123`

### 5. 验证登录状态
在Console控制台输入：

```javascript
// 检查当前角色和权限
console.log('Role:', AUTH.role);
console.log('Payroll Access:', AUTH.payrollAccess);
console.log('Token exists:', !!AUTH.token);
```

**应该看到：**
```
Role: biz_super_admin
Payroll Access: true
Token exists: true
```

### 6. 测试薪资访问
1. 点击左侧导览"薪酬"分类
2. 点击"工资" > "薪资核算表"
3. **应该弹出"薪资数据访问确认"弹窗**

### 7. 如果还是不弹窗，检查控制台
在Console中查看是否有JavaScript错误，并提供截图

---

## 🐛 Debug命令

如果上述步骤完成后还是不工作，在Console中运行：

```javascript
// 验证函数是否存在
console.log('isPayrollL3 exists:', typeof isPayrollL3 === 'function');
console.log('ensurePayrollAccess exists:', typeof ensurePayrollAccess === 'function');

// 测试薪资L3检测
console.log('l3-4-1-1 is payroll:', isPayrollL3('l3-4-1-1'));

// 手动触发一次
if(AUTH.role === 'biz_super_admin') {
  ensurePayrollAccess({target_ref: '测试', entry: '薪资核算表'}).then(ok => {
    console.log('Manual trigger result:', ok);
  });
}
```

---

## 📸 如果还是不工作

请提供以下信息的截图：
1. Console中 `AUTH` 对象的完整内容
2. Console中是否有红色错误信息
3. Network面板中点击薪资分类时的请求记录
