# SDD V6 多智能体协作架构

## 概述

SDD V6 使用三个专业化子智能体完成从设计到交付的全流程开发：

| 智能体 | 模型 | 职责 | 输入 | 输出 |
|--------|------|------|------|------|
| **Planner** | gpt-5.5 | 任务拆分 | PRD、Plan、API 契约 | `.sdd/tasks.json` |
| **Developer** | claude-opus-4-7 | 代码实现 | 任务定义 + 经验库 | 代码文件 + 经验积累 |
| **Tester** | claude-sonnet-4-6 | 验证代码 | 验收标准 + 代码 | 测试报告 + 状态更新 |

编排器（Orchestrator）是用户打开的主 Agent 窗口，通过 `/sdd-start` 命令注入编排身份。

## 通信机制

### 核心原则

**子智能体之间不直接通信**，而是通过**共享文件系统**进行异步协作。

编排器通过 Cursor 的 `Task` 工具调度子智能体：
- 父→子：通过 `prompt` 参数传递任务指令和文件路径
- 子→父：子智能体完成后返回一段文字摘要（文件路径列表、PASS/FAIL 等）
- 子→子：不存在直接通信，通过文件中转（tasks.json、test-reports、experience.md）

### 关键文件

```
<active_project_path>/
├── .sdd/
│   ├── tasks.json           # 任务状态机（核心通信中枢）
│   ├── experience.md        # 经验库（Developer 读写）
│   └── test-reports/        # 测试报告（Tester 写 → Developer 读）
│       ├── test-T-001.md
│       └── test-T-002.md
├── docs/
│   ├── PRD.md              # 产品需求（只读）
│   ├── Plan.md             # 开发计划（只读）
│   └── api-contracts.md    # API 契约（只读）
└── [代码目录]
```

## 工作流程详解

### 阶段 1：任务拆分（Planner）

**触发**：编排器调用 `Task(subagent_type="planner", ...)`

**输入**：
- `docs/PRD.md`（产品需求）
- `docs/Plan.md`（开发计划）
- `docs/api-contracts.md`（API 契约）

**处理**：
1. 读取所有设计文档
2. 将功能拆分为独立、可验证的任务
3. 确定任务依赖关系和优先级
4. 为每个任务指定规范文件（`rules_files`）

**输出**：`.sdd/tasks.json`

### 阶段 2：开发循环（Orchestrator → Developer → Tester）

**触发**：Planner 完成后，编排器自动开始循环。

#### 2.1 选择任务（Orchestrator）

编排器从 tasks.json 中选取：
- status = "pending"
- blocked = false
- 所有 dependencies 均已 passed
- priority 最小的那个

#### 2.2 实现代码（Developer）

**调用方式**：
```
Task({
  description: "开发任务 T-001",
  prompt: "项目路径：...\n任务 ID：T-001\n...",
  subagent_type: "developer",
  run_in_background: false
})
```

**Developer 内部流程**：
1. 读取 experience.md，避免重复踩坑
2. 读取 tasks.json 中的任务定义
3. 读取 rules_files 指定的规范文件
4. 按分层顺序开发
5. 运行 lint / typecheck
6. 追加经验到 experience.md

**返回给编排器**：修改/新增的文件路径列表

#### 2.3 验证代码（Tester）

**调用方式**：
```
Task({
  description: "验证任务 T-001",
  prompt: "项目路径：...\n任务 ID：T-001\nDeveloper 产出的文件：[...]",
  subagent_type: "tester",
  run_in_background: false
})
```

**Tester 内部流程**：
1. 读取 acceptanceCriteria
2. 逐条独立验证
3. 对照规范文件检查
4. 写入测试报告

**返回给编排器**：PASS / FAIL + 报告路径

#### 2.4 修复循环（如果失败）

```
Tester 报告 FAIL
     ↓
编排器检查 retry_count
     ↓
  < 3 次？
   ↙    ↘
 Yes     No
  ↓      ↓
调用     标记 blocked
Developer    ↓
(prompt 附带   请求人工介入
 test-report
 路径)
  ↓
调用 Tester 复验
```

修复时编排器的调用：
```
Task({
  description: "修复任务 T-001",
  prompt: "项目路径：...\n任务 ID：T-001\n这是修复任务。\n测试报告在：.sdd/test-reports/test-T-001.md\n请读取报告，针对性修复。",
  subagent_type: "developer",
  run_in_background: false
})
```

每次修复都是一个新的 Developer 实例，通过读取 test-report 文件恢复上下文。

### 阶段 3：完成交付（Orchestrator）

**条件**：所有任务 status = "passed"（或部分 blocked）

**输出**：
1. 开发完成报告
2. `docs/startup.md`（环境要求、启动命令）
3. 提示用户进行业务验收

## 状态机流转

```
任务生命周期：

    pending (初始)
       ↓
  in_progress (Developer 开始)
       ↓
    testing (Tester 验证中)
       ↓
   ┌───┴───┐
   ↓       ↓
 PASS     FAIL
   ↓       ↓
 passed  fixing (retry_count++)
           ↓
      retry < 3?
       ↙     ↘
     Yes      No
      ↓       ↓
  in_progress  blocked (人工介入)
```

## 智能体调用语法

### Cursor Task Tool

```typescript
Task({
  description: "任务描述（简短）",
  prompt: "详细指令（含项目路径、任务 ID、需要读取的文件等）",
  subagent_type: "planner" | "developer" | "tester",
  run_in_background: false
})
```

关键点：
- `subagent_type` 必须和 `.cursor/agents/` 下文件的 `name` 字段一致
- `prompt` 是子智能体唯一的输入来源，必须包含足够的路径和上下文指引
- 子智能体返回的是文字摘要，不是结构化数据
- 每次调用都是新的上下文，子智能体不保留历史

## 关键设计原则

### 1. 单一职责
- Planner：只拆任务，不写代码
- Developer：只写代码，不验证
- Tester：只验证，不修复
- Orchestrator：只调度，不读代码

### 2. 文件系统通信
子智能体通过文件系统异步通信，编排器通过 Task 工具同步调度。

### 3. 状态驱动
`tasks.json` 是唯一的状态真相来源。

### 4. 经验积累
Developer 通过 `experience.md` 积累经验，避免重复犯错。

### 5. 独立验证
Tester 不信任 Developer 的任何声明，独立验证所有验收标准。

### 6. 有限重试
最多重试 3 次，超过则标记为 blocked，请求人工介入。

## 与 Cursor 能力的对应关系

| SDD 概念 | Cursor 能力 |
|----------|------------|
| Orchestrator | 父 Agent（用户聊天窗口） |
| 子智能体调用 | `Task` 工具 |
| 子智能体定义 | `.cursor/agents/*.md` |
| 通信中枢 | 项目文件系统（.sdd/） |
| 开发规范 | `.cursor/dev-standards/*.mdc` |
| 产品设计 | `.cursor/skills/sdd-product-design/` |
| 命令入口 | `.cursor/commands/sdd-*.md` |

## 局限性

1. **无并行开发**：当前串行执行避免文件冲突，未来可基于 git worktree 支持
2. **无跨会话记忆**：子智能体每次调用是新上下文，只能靠文件恢复
3. **无移动端规范**：移动端项目需用户自备开发规范
4. **Tester 不执行代码**：只做静态检查和逻辑验证，不跑真实测试
