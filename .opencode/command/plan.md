---
description: Plan mode — produce a written implementation plan (files, signatures, acceptance criteria) for a task. Read-only; no code changes.
agent: plan
---

You are the planning step of the Ask My Filings workflow. Produce a written plan, do not implement it.

1. Read `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DECISIONS.md`, `docs/PROJECT_MEMORY.md`, `docs/execution-plan.md`.
2. For the task, output a plan containing:
   - Exact file paths to create or modify
   - Function signatures / module responsibilities (no full implementations, at most ~15 lines of illustrative code)
   - Inputs, outputs, and data flow per file
   - Acceptance criteria (how the work will be verified)
   - Which phase of the execution plan this belongs to
3. Rules:
   - Architecture is locked — do not redesign. If the task conflicts with a locked decision, say so and stop.
   - Flag explicitly any step that touches a Hard Constraint (ratio computation, refusal logic, chunking rules, LangGraph topology, retry cap, faithfulness threshold, concept map, golden-set answers).
   - If ambiguous, state the assumption you are making and proceed.
   - Do not modify any files.

Plan this task:

$ARGUMENTS