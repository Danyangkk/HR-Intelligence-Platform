# 阶段 B2：原型设计

**严格按照 ui-design-spec.md 中的描述设计，不得自由发挥。**

## 设计规范底座（必须加载）

**无论使用 Stitch 还是 Pencil MCP，进入 B2 时必须先加载 UI Design Standard Skill（位于 `harness-core/skills/ui-design-standard/SKILL.md`）作为设计底层规范。**

该 Skill 定义了：
- 字阶策略（标题 Outfit + 正文 Geist/Inter，标题字距 -0.04em）
- 圆角克制（核心组件 8px，严禁 >12px 软圆角）
- 布局效率（数据密集场景使用对称 4 列/3 列网格）
- 语言策略（所有显示文字必须全中文，禁止英文占位符）
- 色彩与对比（Off-Black #18181B，Tonal Focus 建立视觉锚点）
- M3 交互状态（五态）

**所有原型产出必须通过该 Skill 的验证清单后才能提交用户确认。**

## 工具选择（必须询问用户）

**进入 B2 时必须先询问用户**：「请选择原型设计工具：Stitch 还是 Pencil MCP？」**未经用户明确回答，不得开始设计。**

| 方式 | 工具 | 输出格式 | 特点 |
|------|------|---------|------|
| **Stitch** | Google Stitch | HTML + TailwindCSS（.zip） | 速度快，输出代码可直接参考开发 |
| **Pencil MCP** | 内置 Pencil | .pen 文件 | 无需外部工具，全在编辑器内完成 |

---

## 模式 A：Stitch

### 步骤 1：生成 Stitch 提示词

**整体生成**，每个界面基于 B1 阶段确定的风格生成 **1 段英文提示词**，最后**整合输出最终提示词**。

AI 阅读 `ui-design-spec.md`，为每个界面生成英文提示词，必须包含：

```
1. 页面类型与用途
2. 视觉风格（融入 V6.1 规范）
   → 配色（Primary/Secondary/CTA/Background/Text/Border 色值）
   → 字体（标题 Outfit + 正文 Geist/Inter，标题 Track-tight -0.04em）
   → 圆角 8px（radius-sm），严禁 >12px
   → Off-Black #18181B，核心指标使用 Tonal Focus
   → 注入 Stitch VIBE: "Industrial Refinement / Clinical Curator"
3. 布局结构
4. 组件清单及细节
5. 示例数据（列表至少 3 条，对话至少 2-3 轮，表格至少 3-5 行）
6. 视口（桌面端 1440×900 或 移动端 390×844）
```

**提示词模板**：

```
**VIBE & ATMOSPHERE:** Industrial Refinement / Clinical Curator.
**STITCH DESIGN SYSTEM:**
- Platform: [Web/Mobile], [Desktop]-first
- Palette: [Primary Name] (#hex), Canvas [#hex], Off-Black #18181B
- Typography: Headings Outfit (Track-tight -0.04em) + Body Geist/Inter
- Geometry: MANDATORY 8px corners (radius-sm), symmetric-grid for data dashboards
- Tonal Focus: High-contrast fill for hero metrics

**Layout**: [Layout description from spec]

**Components**:
- [Area]: [Component type] — [Specific content and data]
...

**Sample Data** (ALL IN CHINESE):
- [Real data 1 in Chinese]
...

Desktop viewport, 1440×900.
```

将提示词**在对话中呈现**给用户（不落盘），告知：「已生成 Stitch 提示词，请复制到 Stitch 中生成界面。」

### 步骤 2：用户在 Stitch 中生成并导出

用户操作（AI 给出指引）：
1. 打开 stitch.withgoogle.com
2. 粘贴提示词 → 生成界面
3. 点击 More → Download 下载 .zip
4. 解压到 `docs/prototypes/` 下对应目录

**文件规范**：

```
docs/prototypes/
├── 01-登录页/
│   ├── index.html
│   └── style.css (TailwindCSS)
├── 02-仪表盘/
│   └── ...
└── ...
```

命名规则：`NN-界面名/`，NN 为两位序号。

### 步骤 3：AI 验证

每个界面导入后，AI 读取 HTML/CSS 文件：
- 对照 ui-design-spec.md 的组件清单逐项核对
- 检查示例数据完整性
- 检查布局结构是否与 spec 一致
- 标注缺失或偏差

逐界面确认：「界面 [N/总数]『[界面名]』已验证，请确认或修改。」

### 步骤 4：完成收尾

1. 全部界面完成后，删除临时文件 `.sdd/tmp/ui-design-spec.md`
2. 发起最终确认：「所有界面原型已完成，确认后进入阶段 C。」

---

## 模式 B：Pencil MCP

### 准备工作

1. **加载 UI Design Standard Skill V6.1**
2. 阅读 `ui-design-spec.md` 中的风格调研摘要
3. 调用 `get_guidelines("web-app")` 获取 Pencil 设计指南
4. 调用 `get_style_guide_tags` → `get_style_guide(tags)` 获取风格参考
5. 调用 `open_document("new")` 创建新画布
**如果Pencil MCP 连接失败，告诉用户：「可以自行前往pencil 绘制原型图，后将.pen文件保存至项目路径下的docs/prototypes文件夹下」并且提供用户可直接复制走提供给pencil工作的提示词,提示词要保存在docs/prototypes文件夹下（完备描述项目的页面逻辑及设计规范）**
### 批量绘制

**允许一次性绘制全部界面，不需要每个界面单独门禁。**

执行要求：

1. 阅读 ui-design-spec.md 中全部界面描述
2. 为每个界面创建 1 个独立 Frame，命名为 `NN-界面名`，尺寸 1440×900
3. 所有 Frame 必须在同一画布中有序排列，禁止重叠
4. 每个 Frame 严格按组件清单和示例数据绘制
5. 全部界面绘制完成后，再统一截图验证、保存、发起 B2 阶段门禁

### Pencil 画布布局硬规则

所有界面 Frame 必须在同一画布中横向排列或网格排列，不得重叠。

默认采用横向排列：

```text
01-登录页：x=0, y=0, width=1440, height=900
02-主界面：x=1680, y=0, width=1440, height=900
03-员工端页面：x=3360, y=0, width=1440, height=900
04-坐席端页面：x=5040, y=0, width=1440, height=900
05-知识库管理页面：x=6720, y=0, width=1440, height=900
```

如果界面超过 5 个，可改用网格排列：每行最多 3 个，水平间距 240，垂直间距 240。

也可以在插入新界面前调用 `find_empty_space_on_canvas(direction="right", width=1440, height=900, padding=240)` 找空位。

禁止：

- 不指定 `x/y` 就插入新的界面 Frame
- 把多个界面放在同一个 Frame 内
- 把多个 1440×900 Frame 放在同一坐标
- 为了节省空间缩小界面 Frame 尺寸

### B2 阶段门禁

全部界面绘制完成后，必须执行统一验证：

1. 调用 `snapshot_layout(problemsOnly=true)` 检查是否存在重叠、裁切、布局异常
2. 对关键界面调用 `get_screenshot` 核对
3. 对照 ui-design-spec.md 的组件清单逐项核对
4. 确认所有 Frame 坐标不同，且排列清晰
5. 提醒用户 ⌘+S 保存当前 `.pen` 文件

统一确认文案：

```text
阶段 B2 原型已完成，共 [N] 个界面。
我已检查：Frame 不重叠、尺寸一致、组件与说明书一致。
请保存 .pen 文件到 docs/prototypes/，并确认是否进入阶段 C。
```

**未经用户明确确认“进入阶段 C”，不得执行阶段 C。**

### 完成收尾

1. 提醒用户将 .pen 文件保存到 `docs/prototypes/`
2. 删除临时文件 `.sdd/tmp/ui-design-spec.md`
3. 发起最终确认

---

## 质量要求（两种模式通用）

- 每个界面生成 1 版可视化原型
- 列表/卡片至少 1 条示例数据
- 对话界面至少 1 轮气泡消息
- 禁止用 Markdown 文字描述充当原型
- 禁止不看设计说明书直接画
- **V6.1 规范检查（必须全部通过）：**
  - [ ] 所有显示文字是否全中文（禁止英文占位符）
  - [ ] 圆角是否控制在 8px-12px 以内（严禁 >12px）
  - [ ] 数据密集场景是否使用对称等分网格布局
  - [ ] 核心指标卡是否使用 Tonal Focus（高对比填充色）
  - [ ] 标题是否使用 Outfit + Track-tight 紧凑排版

输出到：
- Stitch 模式：`docs/prototypes/NN-界面名/`（HTML+CSS）
- Pencil 模式：`docs/prototypes/*.pen`

**未经用户确认，不得进入阶段 C。**
