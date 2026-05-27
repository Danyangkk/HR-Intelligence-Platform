# Platform Adapters

SDD Harness V7 uses one core and three thin platform adapters.

## Core

The only source of truth is:

```text
harness-core/
```

Core files contain platform-neutral rules for routing, product design, development loop, agents, skills, and dev standards.

## Codex

Codex entry files:

```text
AGENTS.md
.codex/README.md
.codex/config.toml
.codex/agents/planner.toml
.codex/agents/developer.toml
.codex/agents/tester.toml
.codex/commands/*.md
```

Codex subagents are configured as TOML files. Their `developer_instructions` must only point to `harness-core/agents/*.md`.
Codex command files are thin adapters. They must only point to `harness-core/commands/`, `harness-core/skills/`, or `harness-core/protocols/`.

If a Codex runtime does not support custom subagent TOML, follow:

```text
harness-core/protocols/codex-subagents.md
```

## Claude Code

Claude Code entry files:

```text
.claude/CLAUDE.md
.claude/agents/*.md
.claude/commands/*.md
```

Claude files are adapters. They must only point to `harness-core/`.

## Cursor

Cursor entry files:

```text
.cursor/rules/*.mdc
.cursor/agents/*.md
.cursor/commands/*.md
.cursor/skills/**
.cursor/dev-standards/*.mdc
```

Cursor files are adapters. They must only point to `harness-core/`.

## Project Directories

Managed projects under `Projects_Repo/<project-id>/` must not contain copied platform adapters:

```text
Projects_Repo/<project-id>/.cursor/
Projects_Repo/<project-id>/.claude/
Projects_Repo/<project-id>/.codex/
```

Project-local state belongs in:

```text
.sdd/
docs/
frontend/
backend/
mobile/
```
