# /sdd-bugfix - BUG 修复

## 阶段说明

当开发过程中遇到 BUG 时，使用此命令进入修复流程。

## 使用方式

```
/sdd-bugfix <问题描述>
```

**示例**：
```
/sdd-bugfix 登录页点击登录按钮后没有反应，控制台报错 "Cannot read property 'token' of undefined"

/sdd-bugfix 后端接口返回 500 错误，日志显示数据库连接失败

/sdd-bugfix 首页列表数据加载很慢，有时候会超时
```

## 执行流程

1. **加载 Skill** - 读取 `harness-core/skills/sdd-bugfix/SKILL.md`
2. **记录用户原话** - 完整保存用户描述的问题
3. **经验回查** - 检索 `.sdd/experience.md`，判断是否已有相同/相似问题经验
4. **重复犯错分析** - 如果 experience.md 已有相关经验，必须分析为什么仍然犯错
5. **问题分析** - 翻译精简问题，定位可能原因
6. **排查修复** - 检查相关代码，定位并修复 BUG
7. **生成文档** - 将修复过程记录到 `.sdd/bug_fix/` 目录
8. **经验更新** - 将本次 Bug 的原因、修复方式、避免复发规则追加或更新到 `.sdd/experience.md`

## 产出物

| 文件 | 内容 |
|------|------|
| `.sdd/bug_fix/问题编号-问题简述.md` | BUG 修复报告 |

## 执行指令

执行 `harness-core/skills/sdd-bugfix/SKILL.md` 中的流程。

## 完成后

告知用户：

```
BUG 已修复！

问题：[简述]
原因：[根本原因]
方案：[修复方案]

修复报告已存档：.sdd/bug_fix/问题编号-xxx.md

修改的文件：
- [文件列表]

经验更新：
- [新增/更新到 experience.md 的规则摘要]
```
