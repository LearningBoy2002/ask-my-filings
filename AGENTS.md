# Ask My Filings Agent Rules

Read first:

docs/ARCHITECTURE.md
docs/TECH_DECISIONS.md
docs/PROJECT_MEMORY.md
docs/execution-plan.md

Architecture decisions are locked.

Do not redesign the system.

Implement only the requested task.

Only modify files explicitly listed in the prompt.

Write tests whenever implementation code is added.

Before completion:
- run tests
- verify requirements
- report files changed
- always update project memory file after any code updation.