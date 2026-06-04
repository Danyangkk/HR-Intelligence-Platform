# hr-intelligence-platform

> HR data platform & multi-agent system that gets smarter with use — through a human-in-the-loop improvement harness (trace, auto-retrospective, ticket workflow, test gate). LangGraph-based agent with role-separated views, payroll TTL compliance, and full audit trail. Built for production governance, not just demos.

中文版 / Chinese version: [README.zh-CN.md](./README.zh-CN.md)

---

## Why this project

Most LLM agent demos stop at "it works on a happy path." This project goes further: it treats an agent as a **production system that must be governed, audited, and continuously improved** — especially in a sensitive domain like HR, where wrong answers cost real money and exposing salary data is a compliance incident.

The core question it answers: **how do you make an AI agent get smarter over time without letting it modify itself?**

The answer here is a **human-in-the-loop improvement harness** — real usage produces traces and feedback; a retrospective agent groups bad cases into actionable findings; a business admin decides what's worth fixing; a tech admin makes the change; a test gate guards against regressions; once released, the finding is marked fixed. The agent gets smarter every week, but every change is reviewed, gated, and auditable.

## Screenshots

**Data platform** — 84 L3 categories across 4 source types, with payroll category locked from non-authorized roles.
![Data Platform](docs/screenshots/01-data-platform.png)

**Super agent** — multi-agent orchestration with provenance panel; the agent classifies intent semantically and refuses to fabricate when retrieval yields no hit.
![Super Agent](docs/screenshots/02-agent.png)

**Retrospective report** — weekly findings with dual-layer output: plain-language summary for the business admin, technical clues (node path, run IDs) for the tech admin.
![Retrospective](docs/screenshots/03-retrospective.png)

**Improvement tickets** — ticket workflow with source lineage back to the originating finding; nobody (not even the tech admin) can ship past a red test gate.
![Tickets](docs/screenshots/04-tickets.png)

*All entities in screenshots are mock data.*

## Key features

**1. HR Data Platform**
- 84 L3 data categories across 4 source types (Feishu sync, manual upload, rules, reports)
- Three fixed business units; consistent dimension across the whole system
- File parsing (SheetJS), data preview, lineage

**2. Multi-agent System (LangGraph)**
- Planner (semantic routing, no keyword enumeration) + Supervisor (deterministic dispatch)
- 5 reusable agents: Resolver, Retriever, Analyst, Composer, Critic
- Extensible Skills (11 general + 7 flow) and 8 Tools
- RAG over policy docs (Qwen embedding + hybrid retrieval + rerank); refuses to fabricate when 0-hit

**3. Production-grade Governance Harness**
- **Trace** every run with node-level decisions, tool calls, status (no sensitive originals; queries hashed)
- **Auto-retrospective agent** (weekly) clusters bad cases into findings with dual-layer output: a *business summary* for the business admin (plain language — "what's wrong, how bad, priority") and *technical detail* for the tech admin (phenomenon, root-cause hypothesis, node clues, evidence run IDs)
- **Improvement ticket workflow**: accept / reject / hold; tickets carry source lineage back to the originating finding; status machine: pending → in-progress → awaiting-gate → released, with auto-rollback on gate failure
- **Test gate (CI)** as a hard rule: nobody — not even the tech admin — can ship past a red gate; enforced on the backend, not just the UI
- **Eval harness** with three layers (intent accuracy, retrieval hit, answer quality via LLM-as-judge); scheduled + on-demand
- **Hold list** for findings under deliberation, with cross-week recurrence reminders ("this issue was on hold last week, occurred N times this week — please re-evaluate")

**4. Role-separated Governance (3 roles)**
- **Business admin (HRD)**: makes decisions on findings, sees plain-language summaries, owns payroll access (job-bound, with 30-min TTL re-confirmation per action, fully audited)
- **Tech admin**: builds and operates the system; processes improvement tickets; *never* sees payroll figures even with system access (defense-in-depth)
- **Staff**: reads/writes operational data; payroll permanently isolated (rejected at intent classification, fields masked, category hidden)
- Same data, different views: the retrospective report is *plain business language* for the business admin and *full technical detail* for the tech admin — built from one set of findings with two presentation modules

**5. Compliance & Safety**
- Payroll 30-minute TTL re-confirmation (single state shared between data platform and agent)
- Comprehensive audit trail (who, when, what entity, which fields, why) — never logs payroll figures themselves
- Defense in depth: LLM semantic judgment as primary, keyword safety net as fallback (fail-closed only)
- Role normalization with fail-safe fallback to lowest privilege

## Architecture

```
┌─────────────── Data Platform ───────────────┐    ┌─── Super Agent (LangGraph) ───┐
│  84 L3 categories · 4 source types          │    │  Planner → Supervisor → 5     │
│  Feishu / Upload / Rules / Reports          │◄───┤  Agents + Skills + Tools      │
│  Audit · TTL · Role-based access            │    │  RAG over policy docs         │
└────────────────────┬────────────────────────┘    └──────────┬────────────────────┘
                     │                                         │
                     │  every run produces trace               │
                     ▼                                         ▼
              ┌─────────────────── Improvement Harness ────────────────────┐
              │ Trace + 👍👎 → Retrospective Agent (weekly)                 │
              │   ├─ Business summary (biz admin decides)                  │
              │   └─ Technical detail (tech admin executes)                │
              │ Accept → Improvement Ticket → Test Gate → Release          │
              │   └─ on-release: backfill finding/badcase status = fixed   │
              │ Eval harness (intent / retrieval / answer quality)         │
              └─────────────────────────────────────────────────────────────┘
```

## Tech stack

- **Backend**: Python · FastAPI · PostgreSQL (pgvector) · Celery · LangGraph
- **LLM**: Qwen (embedding + chat); LLM-as-judge for Eval layer 3
- **Frontend**: Vanilla HTML/JS (data platform UI + agent UI + retrospective/eval/ticket pages)
- **Deployment**: Docker Compose
- **Data**: mock entities throughout (the framework is real, the data is fictional)

## Repository layout

```
.
├── backend/                  # FastAPI service, agent runtime, harness
│   ├── src/
│   │   ├── services/         # business services
│   │   ├── workers/          # Celery workers (retrospective, eval)
│   │   └── main.py
│   ├── tests/                # router_cases, regression tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # Vanilla HTML/JS UI
│   ├── index.html            # main app (data platform + agent)
│   └── permission-admin.js   # role/permission management
├── docs/                     # Design documents
│   ├── screenshots/          # README screenshots
│   ├── 前端页面规格-权限重构.md   # Frontend & permission spec
│   ├── 复盘Agent实现规格.md       # Retrospective agent spec
│   └── ...                   # router / prompts / harness / SOP specs
├── nginx/                    # reverse proxy config
└── docker-compose.yml
```

## Quick start

```bash
# 1. Clone
git clone https://github.com/<your-username>/hr-intelligence-platform.git
cd hr-intelligence-platform

# 2. Configure env
cp backend/.env.docker.example backend/.env.docker
# edit to set: Qwen API key, JWT secret, Postgres password

# 3. Run
docker compose up -d

# 4. Open
# Frontend: http://localhost:8080
# Backend API docs: http://localhost:8080/api/v1/docs
```

Default test accounts (mock):
- Business admin (HRD): `biz_hrd`
- Tech admin: `developer`
- Staff: `staff_user`

## Design philosophy

A few principles that shaped the system:

- **Semantic routing, no keyword enumeration.** Keyword lists are brittle and incomplete; intent classification is done by LLM with semantic judgment. Keywords are kept only as a fail-closed safety net.
- **Job-bound permissions, no granular grants.** Salary access comes with the business admin role, not an additional flag a tech admin can hand out — that would defeat the separation of duties.
- **Defense in depth.** Sensitive checks (e.g. payroll) live as a *pre-gate before any routing branch*, not scattered across handlers — closing the back-doors where old rules could bypass new policy.
- **The retrospective agent does not auto-fix.** It surfaces findings; humans decide; gates enforce. "Getting smarter" without losing accountability.
- **Two readers, two presentations, one source of truth.** Same finding, two modules: business summary for decisions, technical detail for execution.
- **Audit everything that touches sensitive data, log nothing sensitive itself.** Audit records *who looked at what entity for which reason* — never the salary figure itself.

## Status

This is a portfolio-grade project: the framework is production-shaped (permissions, audit, harness, gate, eval) and the data is mock. The full improvement loop is operational end-to-end on mock data.

## License

MIT — see [LICENSE](./LICENSE).

## Author

**Danyang** · 18346103232@163.com

---

*Built as an exploration of what a production-grade AI agent system looks like when it has to be governed, audited, and continuously improved — not just demoed.*
