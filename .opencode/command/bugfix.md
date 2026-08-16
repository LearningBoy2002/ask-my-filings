---
description: Fix a bug — reproduce, minimal fix, regression test, verify. Only listed files.
---

You are fixing a bug in the Ask My Filings project. Work order:

1. Reproduce the reported failure first (run the relevant code/test). If you cannot reproduce, say so and report the attempted reproduction steps rather than guessing at a fix.
2. Read `AGENTS.md` and the memory files (`docs/ARCHITECTURE.md`, `docs/TECH_DECISIONS.md`, `docs/PROJECT_MEMORY.md`).
3. Find the root cause, then apply the MINIMAL fix:
   - Modify only the files needed for the fix, plus a regression test. Do not refactor unrelated code.
   - If the fix touches a Hard Constraint (financial values, refusal behavior, retry cap), the fix must preserve the constraint exactly — "Insufficient data"/refusal behavior is correct, not a bug to optimize away.
   - Add a regression test that fails without the fix and passes with it.
4. Before finishing: run the full relevant test suite, verify the original failure is gone, and report files changed + root cause in one or two lines.

Bug report:

$ARGUMENTS