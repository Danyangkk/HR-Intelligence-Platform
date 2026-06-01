# 🔍 快速测试：业务超管能否看到薪资分类

## 在Console中执行以下命令：

```javascript
// 1. 确认当前角色
console.log('当前角色:', AUTH.role);
console.log('应该看到薪资分类:', AUTH.role === 'biz_super_admin');

// 2. 检查 canViewPayrollNav 函数
if(typeof canViewPayrollNav === 'function') {
  console.log('canViewPayrollNav()结果:', canViewPayrollNav());
} else {
  console.error('❌ canViewPayrollNav函数不存在');
}

// 3. 检查分类树
if(typeof filterCategoryTree === 'function' && typeof categoryTree !== 'undefined') {
  const filtered = filterCategoryTree(categoryTree);
  const payrollCat = filtered.find(l1 => l1.id === 'l1-4');
  console.log('薪酬分类:', payrollCat);
  if(payrollCat) {
    console.log('  - 是否disabled:', payrollCat.disabled);
    console.log('  - 子分类数量:', payrollCat.children?.length);
  } else {
    console.error('❌ 找不到薪酬分类');
  }
} else {
  console.error('❌ filterCategoryTree或categoryTree不存在');
}

// 4. 向下滚动左侧导航，找"薪酬"分类
console.log('✅ 请向下滚动左侧导航栏，查找"薪酬"分类');
```

## 预期结果：

**业务超管（biz_super_admin）**应该看到：
```
当前角色: biz_super_admin
应该看到薪资分类: true
canViewPayrollNav()结果: true
薪酬分类: {id: 'l1-4', name: '薪酬', children: Array(5), disabled: undefined}
  - 是否disabled: undefined
  - 子分类数量: 5
```

**技术超管/普通员工**应该看到：
```
canViewPayrollNav()结果: false
薪酬分类: {id: 'l1-4', name: '薪酬', children: Array(5), disabled: true}
  - 是否disabled: true  ← 置灰
```

## 如果结果正确但看不到薪酬分类

请在左侧导航栏**向下滚动**，薪酬分类在列表底部！

顺序应该是：
1. 管理制度
2. 员工关系
3. 组织文化
4. **薪酬** ← 在这里！
