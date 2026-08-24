# Core Architecture

This document describes the baseline architecture for `qgis_ai_agent.core`.

## Goals

- keep `plugin.py` thin and focused on QGIS bootstrap/wiring
- isolate orchestration, planning, execution, routing, and LLM transport
- keep planning JSON contract stable for UI and tools
- allow adding new tool domains without rewriting orchestration

## Package Layout

- `core/orchestrator/` - flow coordinator and session state
- `core/chat/` - chat-mode prompt and message builder
- `core/planning/` - planning prompt, parser, clarification, planning service
- `core/execution/` - step execution service and execution context
- `core/routing/` - intent policies and router
- `core/llm/` - transport client and worker thread
- `core/context/` - project context providers
- `core/state/` - shared stores (history)

## Runtime Flow

1. `QgisAiAgentPlugin` initializes `LayoutAgentDockWidget` and `CoreOrchestrator`.
2. `CoreOrchestrator` receives UI events (`prompt`, `confirm`, `cancel`).
3. Router selects mode (`chat` or `action`).
4. Service builds LLM messages and sends async request through `LLMWorkerThread`.
5. Planning response is parsed/validated, then rendered as a confirmable plan.
6. Confirmed steps are executed via tool registry through `ExecutionService`.

## UI Contract

The orchestrator works with a minimal DockWidget API contract:

- add/finalize streaming model messages
- add plan/system/result messages
- toggle busy state and plan buttons
- expose prompt input for clear()

This keeps core independent from concrete widget implementation details.

## Prompt Policy

- system prompts are authored in English
- user-facing fields (`preface`, `plan_description`, clarification text) remain Russian
- JSON shape remains stable:
  - `can_do`
  - `preface`
  - `plan_description`
  - `steps`
  - `clarification_questions`
