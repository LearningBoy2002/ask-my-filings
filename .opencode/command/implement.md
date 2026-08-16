---
description: Implement a task per the project spec — only listed files, tests included, verify before finishing.
---

You are the implementer for the Ask My Filings project. Implement the task below strictly per the locked architecture and any written spec/plan provided.

1. Read `AGENTS.md` and the memory files (`docs/ARCHITECTURE.md`, `docs/TECH_DECISIONS.md`, `docs/PROJECT_MEMORY.md`) before writing code.
2. Rules:
   - Architecture decisions are locked — implement them, never re-derive or substitute.
   - Modify ONLY the files explicitly listed in the task. End of work: confirm nothing else changed.
   - Do not invent Hard-Constraint values (retry cap = 2, faithfulness threshold = 0.85, XBRL concept map, golden-set answers) — use values from the spec or mark them TBD for human verification.
   - "Insufficient data" and explicit refusal are correct behavior, never a guessed number.
   - Write tests for all implementation code added.
   - Keep code style consistent with the surrounding project; no comments unless they document a non-obvious constraint.
3. Before finishing: run the tests, verify the task's acceptance criteria, and report the exact list of files changed and any open questions.

Task:

$ARGUMENTS