---
description: Start a session — load project memory files and report current state before any work begins.
---

You are starting a new session on the Ask My Filings project. Before any work:

1. Read, in order: `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/TECH_DECISIONS.md`, `docs/PROJECT_MEMORY.md`, `docs/DECISION_LOG.md`, `docs/DEV_LOG.md`, `docs/execution-plan.md`.
2. Report back, concisely:
   - Current implementation status (what phase is in progress, what is done vs. not started)
   - The most recent `DEV_LOG.md` entry (what happened last session, what was next)
   - Any open decisions or blockers (embedding model, LLM, etc.)
   - Any Hard Constraints that apply to the upcoming work

Do not modify any files during this command. If the user included a task in the arguments, acknowledge it and propose the next step after reporting state:

$ARGUMENTS