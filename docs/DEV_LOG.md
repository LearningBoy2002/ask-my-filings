# DEV_LOG.md — Ask My Filings

**Owner:** You (from Claude Account #1's session summary).
**Format:** Chronological session-by-session log: what was attempted, what worked, what broke, what's next. Mandatory every session, no exceptions (execution plan Part 6).
**Status:** Phase 0 scaffold.

---

## 2026-08-15 — Phase 0 scaffold

- **Attempted:** Repository scaffold only (execution plan Phase 0): `README.md`, `.env.example`, `.gitignore`, `opencode.json`, `.opencode/agent/` + `.opencode/command/` placeholders, `docs/DECISION_LOG.md`, `docs/DEV_LOG.md`, `docs/DEPLOYMENT.md`, `docs/xbrl_concept_map.md`, `docs/prompts/README.md`, `backend/` skeletons (edgar, ingestion, xbrl, graph/nodes, rag, db, tests, requirements.txt), `frontend/src/`, `eval/golden_set.jsonl`.
- **Worked:** All folders and placeholder files created. No application code, endpoints, SQL, or React code written.
- **Broke:** Nothing.
- **Next:** `git init` if desired; Phase 0 completion checks per execution plan Part 2 — uvicorn hello-world, blank Vite+React app, Supabase `SELECT 1`; lock embedding model and LLM (open decisions, TECH_DECISIONS.md).

## 2026-08-16 — Phase 0 completion tasks (backend prep)

- **Attempted:** Finished the remaining Phase 0 backend prep: updated `backend/requirements.txt` (added `supabase`, `python-dotenv`, `httpx`, `pydantic` — nothing removed), added `backend/db/schema.sql` (placeholder `-- Phase 0 placeholder` + `SELECT 1;` only), and added `backend/db/test_connection.py` (loads repo-root `.env`, validates `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`, creates a Supabase client, performs a read-only PostgREST round trip — no tables, no migrations, no project modifications).
- **Worked:** All three files written; `test_connection.py` passes `py_compile`. FastAPI hello-world, Vite hello-world, and the Supabase project already exist from the prior session.
- **Broke:** Nothing.
- **Next:** Install the new dependencies (`pip install -r backend/requirements.txt`), populate `.env`, then run `python backend/db/test_connection.py` and the Supabase `SELECT 1` check to close Phase 0. Connectivity has NOT been executed yet — the test script is written but unrun. Then Phase 1 (EDGAR client) begins once the embedding model and LLM are locked.

## 2026-08-16 — Phase 0 COMPLETE (all checks passed)

- **Attempted:** Close out Phase 0 by verifying every completion criterion from the execution plan Part 2.
- **Completed checklist:**
  - [x] Repo scaffolded per execution plan Part 6 folder tree (Phase 0 scaffold, 2026-08-15)
  - [x] `backend/requirements.txt` updated — fastapi, uvicorn, supabase, python-dotenv, httpx, pydantic
  - [x] `backend/db/schema.sql` placeholder (`SELECT 1;`) written
  - [x] `backend/db/test_connection.py` written (read-only PostgREST round trip, no tables/migrations)
  - [x] Supabase project created (free tier)
  - [x] `.env` populated with real credentials
  - [x] `python backend/db/test_connection.py` — executed successfully (Supabase reachable, credentials accepted, HTTP 200)
  - [x] `SELECT 1` executed successfully in Supabase SQL Editor
  - [x] FastAPI hello-world boots (verified prior session)
  - [x] Vite+React hello-world boots (verified prior session)
- **Worked:** All four Phase 0 hello-world-style checks from the execution plan Part 2 now pass: uvicorn boots, Vite boots, Supabase connectivity from Python works, SQL editor responds.
- **Broke:** Nothing.
- **Next:** Phase 1 — Data Acquisition (EDGAR client). Deliverables per execution plan: `backend/edgar/client.py` (CIK resolver, submissions fetcher, company-facts fetcher, raw-filing fetcher, rate-limited to 8 req/sec, real User-Agent, exponential backoff on 403/429), `backend/edgar/models.py`, `backend/edgar/cache.py`, `tests/test_edgar_client.py`. Acceptance: fetching Apple's FY2025 10-K (CIK 0000320193) reproduces the manually-downloaded ZIP's content; no 403s across a repeated run. Still open and blocking Phase 2/4: embedding model and LLM decisions (do not silently default).