---
name: ui-design-standard
description: SDD V6 UI 设计标准 Skill。定义原型设计阶段的视觉规范底座，包括字体、圆角、布局、语言、色彩和交互状态。B2 原型设计阶段必须加载此 Skill 作为设计底层规范。
---

# UI Design Standard Skill V6.1

本 Skill 是 SDD V6 原型设计阶段（B2）的设计规范底座。进入 B2 时必须先加载本 Skill，所有原型产出必须通过本 Skill 的验证清单后才能提交用户确认。

---

## 字阶策略

- **标题字体**：Outfit
  - 标题字距：`track-tight -0.04em`
- **正文字体**：Geist / Inter
- 字阶按信息层级递减，确保视觉层次清晰

---

## 圆角克制

- **核心组件圆角**：`8px`
- **严禁**：使用 `>12px` 的软圆角
- 保持界面硬朗、专业的视觉感受

---

## 布局效率

- **数据密集场景**：使用对称等分网格布局
  - 推荐：`4 列` 或 `3 列` 对称网格
- 避免复杂嵌套，保持布局扁平高效

---

## 语言策略

- **所有显示文字必须全中文**
- **禁止**使用英文占位符
- 确保界面语言一致性和用户可读性

---

## 色彩与对比

- **Off-Black**：`#18181B`
- **Tonal Focus**：核心指标使用高对比填充色建立视觉锚点
- 配色方案需在 B1 阶段确定，B2 严格遵循

---

## 交互状态（M3 五态）

所有交互组件必须定义以下五种状态：

1. **Enabled**（可用）
2. **Disabled**（禁用）
3. **Hover**（悬停）
4. **Pressed**（按下）
5. **Focused**（聚焦）

---

## V6.1 规范验证清单

原型产出提交用户确认前，必须通过以下检查：

- [ ] 所有显示文字是否全中文（禁止英文占位符）
- [ ] 圆角是否控制在 8px-12px 以内（严禁 >12px）
- [ ] 数据密集场景是否使用对称等分网格布局
- [ ] 核心指标卡是否使用 Tonal Focus（高对比填充色）
- [ ] 标题是否使用 Outfit + Track-tight 紧凑排版
- [ ] 交互组件是否覆盖 M3 五态

---

## Stitch VIBE 注入

使用 Stitch 生成原型时，提示词中必须注入以下 VIBE：

```
Industrial Refinement / Clinical Curator
```

配合设计系统参数：
- Geometry: MANDATORY 8px corners (radius-sm)
- Typography: Headings Outfit (Track-tight -0.04em) + Body Geist/Inter
- Palette: Off-Black #18181B + Tonal Focus for hero metrics
