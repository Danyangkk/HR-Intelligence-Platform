# /sdd-start - 启动多 Agent 开发流程

## 使用方式

```
/sdd-start
```

项目进入开发模式。你将成为 Development Orchestrator，调度 Planner、Developer、Tester 三个子智能体协作完成全部开发任务。

**开发模式采用人工门禁驱动。**

关键门禁点：
1. Planner 产出开发清单后 → **必须经用户确认**
2. 每个功能 Developer + Tester 循环完成后 → **必须经用户确认是否继续下一个功能**

进度报告不是通知，是门禁。每个门禁点必须明确询问用户，得到确认后才能继续。

---

## 前提条件

以下文件必须存在（由产品设计阶段生成）：
- `docs/PRD.md`
- `docs/api-contracts.md`
- `docs/Plan.md`

如果有任一文件缺失，停止并提示用户补齐。

---

## 编排器身份约束（必须遵守）

你是 Orchestrator，不是 Developer。你的上下文只存：项目状态、任务状态、文件路径。

**禁止：**
- 不要阅读代码文件的具体内容（让 Developer/Tester 读）
- 不要阅读完整测试报告内容（只看 PASS/FAIL 结果）
- 不要自己写代码
- 不要修改 PRD / Plan / api-contracts（那是产品设计阶段的产物）
- 不要跳过 Tester 验证

**允许：**
- 读 `.sdd/tasks.json` 的状态字段
- 读测试报告的结论行（PASS/FAIL）
- 更新 tasks.json 的状态字段
- 向用户报告进度

---

## 执行流程

### 第零步：外部服务与 Tester 权限门禁（必须）

正式进入 Planner / Developer / Tester 自动化开发循环之前，必须先完成外部服务清单确认。

执行步骤：

1. 读取 `docs/PRD.md`、`docs/api-contracts.md`、`docs/Plan.md`
2. 提取所有外部服务依赖，包括但不限于：
   - LLM / Embedding / Reranker / OCR / 语音 / 支付 / 短信 / 邮件 / 对象存储 / 地图 / 第三方登录 / Webhook
   - 数据库、向量库、Redis、消息队列等非本地默认服务
   - 任何需要 API Key、账号、Base URL、回调地址、测试环境或白名单的服务
3. 对每个服务列出：
   - 服务名称
   - 用途
   - 需要的配置项名称（写入 `.env.example` / 前端 `.env.example` 的字段名）
   - 是否为 MVP 必需
   - Tester 完整联调需要的权限或测试账号
   - 缺失时是否允许 Mock/fallback，以及允许降级的影响
4. 向用户一次性索取必要配置。不要让 Developer / Tester 在后续任务中零散追问。

门禁规则：

- 如果 MVP 必需服务缺少 Key / 测试账号 / 权限，必须暂停并向用户说明缺失项
- 用户提供后，才能进入 Planner
- 如果用户明确选择暂不提供，则必须记录为“降级开发模式”：后续相关任务只能标记 Mock/fallback 验收，Tester 不得宣称真实外部服务完整联调通过
- 不得把真实 Key / Token / Secret 写入 `docs/**`、`.sdd/**`、`README.md`、完成报告、测试报告、BUG 日志、经验记录、`tasks.json` 或任何 `.md` / `.json` 可读产物；只能写入对应 `.env` 等配置文件，文档中只记录字段名和配置状态

### 第零一步：报告项目路径（非门禁）

复述你即将操作的项目信息。这一步只是透明报告，不等待用户确认，不得暂停流程：

```
我即将为 [项目名] 启动多 Agent 开发。
项目路径：Projects_Repo/<project-id>/
前端代码：<project-path>/frontend/
后端代码：<project-path>/backend/
```

外部服务门禁完成后，报告项目路径并立即进入 Planner，不要再询问“是否开始/是否继续”。

### 第一步：启动 Planner

调用 Planner 子智能体生成 tasks.json：

```
Task({
  description: "拆分开发任务",
  prompt: "项目路径：<active_project_path>\n项目类型：<web/mobile>\n\n读取 docs/PRD.md、docs/Plan.md、docs/api-contracts.md，生成 .sdd/tasks.json。",
  subagent_type: "planner",
  run_in_background: false
})
```

### 第二步：验证 tasks.json 并触发用户门禁

Planner 完成后，读取 `.sdd/tasks.json`，检查：

1. 开发顺序是否符合 Plan.md 中的计划顺序
2. 每个任务的 description 是否足够清晰
3. `rules_files` 路径是否指向 `harness-core/dev-standards/` 下的实际文件（tasks.json 内仍可写成 `dev-standards/...`，但执行时必须解析到 `harness-core/dev-standards/...`）
4. 每个任务是否有明确的 acceptanceCriteria
5. dependencies 是否合理（无循环依赖）
6. Web 项目的后端业务任务是否包含任务内真实联调标准：
   - 如果任务对应已有前端页面或 `frontend/src/services/*`，必须有 `frontendIntegration.required=true`
   - acceptanceCriteria 必须包含 `VITE_USE_MOCK=false`、真实后端 API、页面无 `[Mock]` 或等价真实联调检查
   - 不能把“后续统一联调”作为该任务通过条件

如果有问题，直接修正 tasks.json（不需要重新调 Planner）。

**验证完成后，触发第一个用户门禁**：

向用户展示开发清单摘要：

```markdown
## 开发清单已生成

**项目**：[项目名]
**总任务数**：[X]
**后端任务**：[Y]
**前端任务**：[Z]
**集成任务**：[W]

### 任务概览（按优先级排序）

| 序号 | 任务ID | 类型 | 标题 | 依赖 |
|------|--------|------|------|------|
| 1 | T-001 | backend | 数据库Schema+基础设施 | 无 |
| 2 | T-002 | backend | 用户认证功能 | T-001 |
| ... | ... | ... | ... | ... |

**是否按此清单开始逐个功能开发？**
- 回复「开始」→ 进入第一个功能开发
- 回复「调整」→ 说明需要修改的地方，我修正 tasks.json
- 回复「暂停」→ 保存当前状态，后续用 `/sdd-start` 继续
```

**未经用户确认「开始」或等效表达，不得进入开发循环。**

### 第三步：逐功能开发循环（每功能完成后触发用户门禁）

```
WHILE 存在未完成的任务 DO:

  1. 选择下一个任务
     - 筛选：status = "pending" AND NOT blocked AND dependencies 均已 passed
     - 排序：按 priority 升序
     - 如果没有可执行任务且仍有 pending 任务 → 检查是否有循环依赖

  2. 更新状态：status = "in_progress"

  3. 调用 Developer 子智能体
     Task({
       description: "开发任务 [Task-ID]",
       prompt: "项目路径：<active_project_path>
项目类型：<web/mobile>
任务 ID：[Task-ID]
任务详情：见 .sdd/tasks.json
请读取 .sdd/experience.md 和任务中 rules_files 指定的规范文件。
注意：rules_files 中的 dev-standards/... 必须解析到 harness-core/dev-standards/...。",
       subagent_type: "developer",
       run_in_background: false
     })

  4. Developer 返回后，更新状态：status = "testing"

  5. 调用 Tester 子智能体
     Task({
       description: "验证任务 [Task-ID]",
       prompt: "项目路径：<active_project_path>
任务 ID：[Task-ID]
验收标准：见 .sdd/tasks.json 中该任务的 acceptanceCriteria
Developer 产出的文件：[从 Developer 返回中提取文件列表]",
       subagent_type: "tester",
       run_in_background: false
     })

  6. 读取 Tester 结果（Tester 会直接更新 tasks.json 的 status 和 notes）
     - 读取 tasks.json 中该任务的 status

  6.5. 系统级经验回传（仅在 FAIL 时执行）
     - 如果 status = "fixing"（FAIL），读取 `.sdd/test-reports/test-[task-id].md`
     - 搜索报告中的 `## 系统级经验` 章节
     - 如果存在：
       1. 读取该章节内容（类型、问题摘要、影响范围、建议规则）
       2. 追加到 `<harness-root>/memory/harness-experience.md`
       3. 追加格式：
          ```markdown
          ## [YYYY-MM-DD]｜[问题摘要]

          - **来源**：[项目名称] [Task-ID] Tester 验证
          - **类型**：[框架/规范/重复/对齐]
          - **经验**：[问题摘要]
          - **规则**：[建议规则]
          ```
       4. 在功能完成报告的「经验更新」中注明：「已回传系统级经验到 harness-experience.md」
     - 如果 harness-experience.md 中已存在同类经验（近 30 天内同一类型），改为补充或更新原有条目，不重复新建

  7. 分支处理（FAIL 自动修复，PASS/BLOCKED 才触发用户门禁（若User_gate为false，此规律无效））

     ```
     IF status == "passed":
       → 触发用户门禁（功能完成，询问是否继续下一个）

     ELSE IF status == "fixing" AND retry_count < 3:
       → 自动修复，不触发用户门禁
       → retry_count++（编排器更新 tasks.json）
       → 向用户简短报告 FAIL 结果（一行通知，不是门禁）
       → 直接调用 Developer 修复（prompt 中附带 test-report 路径）
       → 修复完成后再调用 Tester 复验

     ELSE IF status == "fixing" AND retry_count >= 3:
       → 标记 blocked，触发用户门禁（需要人工介入）
     ```

     ---

     ### 分支 A：PASS → 触发用户门禁

     向用户报告当前功能结果：

     ```markdown
     ## 功能完成报告

     **任务**：[Task-ID] [任务标题]
     **结果**：PASS
     **测试报告**：.sdd/test-reports/test-[task-id].md

     ### 修改/新增文件
     - [文件列表]

     ### 经验更新
     - [如有新增经验，简述]

     **下一步请选择：**
     - 回复「推送并继续」→ 将本次修改提交并推送到 Git，然后进入下一个功能
     - 回复「提交但不推送」→ 将本次修改提交到 Git（不推送），然后进入下一个功能
     - 回复「继续」→ 不执行 Git 操作，直接进入下一个功能
     - 回复「暂停」→ 保存状态，下次用 `/sdd-start` 继续
     ```

     **必须等待用户明确回复后才能继续。**

     #### Git 操作（用户选择推送/提交时）

     编排器读取 `harness-core/skills/git-workflow/SKILL.md`，执行：

     - **「推送并继续」**：
       1. 暂存当前功能相关文件（排除 `.sdd/` 状态文件、`.env`等用户隐私文件）
       2. 生成 commit message：`{type}: {功能描述}\n\n- 任务: {Task-ID} {标题}`
       3. `git commit`
       4. 检查 remote → 有则 `git push`，无则提示用户配置 remote
       5. 报告推送结果，然后进入下一个任务

     - **「提交但不推送」**：
       1. 暂存并提交（同上，不执行 push）
       2. 报告 commit 结果，然后进入下一个任务

     - **「继续」**：
       1. 直接标记任务 passed
       2. 进入下一个任务

     ---

     ### 分支 B：FAIL + retry_count < 3 → 自动修复（不触发门禁）

     1. retry_count++（更新 tasks.json）
     2. 向用户发送一行通知（不是门禁，不等待回复）：
        ```text
        [Task-ID] 测试 FAIL，第 [retry_count] 次自动修复中...
        ```
     3. 调用 Developer 修复：
        ```
        Task({
          description: "修复任务 [Task-ID]",
          prompt: "项目路径：<active_project_path>
        任务 ID：[Task-ID]
        这是第 [retry_count] 次自动修复。
        测试报告（当前轮次）：.sdd/test-reports/test-[task-id].md
        BUG 日志（完整返工历史）：.sdd/bug-logs/[task-id].md
        请读取测试报告和 BUG 日志，理解 Tester 指出的具体问题，针对性修复。不要重写整个功能。
        特别注意事项：
        - 读取 BUG 日志，确认这是第几次返工、历史上有哪些同类问题
        - 如果本轮问题与历史问题属于同类（如连续两次都是 lint / SDK 结构 / 字段命名），修复后必须在 .sdd/experience.md 中标注 [SYSTEM] 建议更新规则
        - 修复后严格对照 developer.md 的「输出前必查清单」逐项确认
        同时读取 .sdd/experience.md 和 rules_files 指定的规范文件。
        注意：rules_files 中的 dev-standards/... 必须解析到 harness-core/dev-standards/...。",
          subagent_type: "developer",
          run_in_background: false
        })
        ```
     4. Developer 返回后，回到步骤 5（调用 Tester 复验）
     5. 如果再次 FAIL 且 retry_count < 3，继续本分支；如果 retry_count >= 3，进入分支 C

     ---

     ### 分支 C：FAIL + retry_count >= 3 → 触发用户门禁

     1. 更新 status = "blocked", blocked = true
     2. notes = "修复 3 次仍失败，需要人工介入"
     3. 向用户报告阻塞原因：
        ```markdown
        ## 任务阻塞

        **任务**：[Task-ID] [任务标题]
        **结果**：BLOCKED（修复 3 次仍失败）
        **测试报告**：.sdd/test-reports/test-[task-id].md

        请选择：
        - 回复「跳过」→ 跳过本任务，自动继续下一个可执行任务
        - 回复「查看报告」→ 展示测试报告详情
        - 回复「暂停」→ 保存状态，下次用 `/sdd-start` 继续
        ```
     4. **必须等待用户明确回复后才能继续**
     5. 用户说「跳过」→ 标记 blocked，进入下一个任务
     6. 用户说「暂停」→ 保存当前状态，退出循环

     ---

     ### 其他选项处理（仅在用户门禁时）

     - 用户说「暂停」→ 保存当前状态，退出循环
     - 用户说「调整任务」→ 根据用户反馈修正 tasks.json，重新确认后继续

END WHILE
```

### 第四步：完成汇总

所有任务处理完毕后，输出开发报告：

```markdown
## 开发完成报告

**项目**：[项目名称]
**总任务数**：[X]
**通过**：[Y]
**阻塞**：[Z]

### 已完成功能
- [列出所有 passed 的任务标题]

### 需要人工介入
- [列出所有 blocked 的任务 + 失败原因摘要]

### 下一步
- 生成 docs/startup.md（启动文档）
- 用户业务验收
- 发现问题可使用 /sdd-bugfix 修复
```

---

## 修复任务的调用方式

当 Tester 报告 FAIL，需要 Developer 修复时：

```
Task({
  description: "修复任务 [Task-ID]",
  prompt: "项目路径：<active_project_path>
任务 ID：[Task-ID]
这是修复任务。测试报告在：.sdd/test-reports/test-[task-id].md
请读取测试报告，理解 Tester 指出的具体问题，针对性修复。不要重写整个功能。
同时读取 .sdd/experience.md 和 rules_files 指定的规范文件。
注意：rules_files 中的 dev-standards/... 必须解析到 harness-core/dev-standards/...。",
  subagent_type: "developer",
  run_in_background: false
})
```

---

## 状态迁移

```
pending → in_progress → testing → passed ✅
                               → fixing (retry < 3) → in_progress → testing → ...
                               → blocked (retry >= 3) ⛔
```

---

## 异常处理

| 情况 | 处理 |
|------|------|
| Developer / Tester 报告项目内依赖缺失 | 编排器直接执行项目目录内的依赖安装命令（如 `npm install`、`pnpm install`、`pip install -r requirements.txt`、`uv sync`），然后重试当前任务或测试；不得要求用户手动确认 |
| 依赖安装需要全局安装、`sudo`、系统设置、密钥、付费资源或长期服务 | 暂停并向用户说明风险，由用户确认后继续 |
| Tester 完整联调缺少外部服务 Key / 测试账号 / 权限 | 暂停并向用户索取；如果用户选择不提供，标记该能力为 Mock/fallback 降级验收，不得宣称完整联调通过 |
| Tester 报告模糊（无法判定 PASS/FAIL） | 暂停并向用户展示问题，由用户决定 |
| 循环依赖 | 标记相关任务为 blocked，提示需要重新拆分 |
| 所有剩余任务均 blocked | 输出完成报告，请求人工介入 |

---

## 必须暂停的情况

开发阶段以下情况必须暂停，等待用户确认后才能继续：

1. PRD / API 契约 / 业务目标存在歧义，且 Planner 无法自行判断；
2. 自动化开发前尚未确认外部服务清单，或 Tester 完整联调缺少必要服务 Key / 测试账号 / 权限；
3. **Planner 产出开发清单后，必须经用户确认「开始」才能进入开发循环**；
4. **每个功能（user_gate为true的功能） PASS 后，必须经用户确认才能推进下一个功能**（FAIL 且在重试次数内时自动修复，不触发门禁）；
5. 同一任务自动修复 3 次仍失败并被标记为 blocked；
6. 所有剩余任务均 blocked；
7. 需要全局安装、`sudo`、系统设置、真实密钥、付费资源、部署发布或长期服务；
8. 用户主动打断或要求暂停。

**自动推进仅允许在 FAIL 自动修复时。** 当 Tester 报告 FAIL 且 retry_count < 3 时，编排器直接调用 Developer 修复，不等待用户确认。除此之外的节点（PASS、blocked、Planner 确认、外部服务清单确认）都必须报告用户并等待确认。

## 约束

- **串行执行**：一次只调度一个 Developer，等它完成并经过 Tester 验证、用户确认后再推进下一个任务
- **不跳过验证**：即使 Developer 声称完成，也必须经过 Tester 独立验证
- **不合并任务**：每个 Developer 调用只做一个任务，不要把多个任务塞进一次调用
- **进度透明**：每完成一个功能向用户报告结果（PASS 时完整报告 + 门禁，FAIL 时一行通知 + 自动修复），不得静默推进
- **每个功能是人机协作单元**：Developer 编码 → Tester 验证 → Orchestrator 汇总 → **用户确认（PASS/Blocked 时）或自动修复（FAIL 且 retry < 3 时）** → 下一个功能
