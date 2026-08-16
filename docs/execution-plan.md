# Ask My Filings — Execution Plan
**No architecture redesign. Execution only.** Architecture stays exactly as locked in ARCHITECTURE.md / TECH_DECISIONS.md / PROJECT_MEMORY.md, amended only by the XBRL-hybrid decision from the prior review. This document is about *how you build it* with the specific free/low-cost toolchain you have.

---

## PART 1 — WORKFLOW DESIGN

Three tools, three distinct jobs. The failure mode to avoid is all three tools trying to "think" about the same problem — that's where free-tier message budgets get burned and where architecture drift creeps in (one tool quietly redesigning something another tool already decided).

### Claude Account #1 — **The Architect**
**Responsible for:**
- Owns the four memory files (ARCHITECTURE.md, TECH_DECISIONS.md, PROJECT_MEMORY.md, and a new DECISION_LOG.md) — the only tool allowed to edit them.
- Turns each roadmap phase into a **written spec**: exact file names, function signatures, inputs/outputs, acceptance criteria — precise enough that OpenCode/DeepSeek can implement without guessing.
- Writes the exact prompt you'll paste into OpenCode for each task.
- Makes any judgment call that touches a Hard Constraint (ratio computation, refusal logic, chunking rules, LangGraph topology).
- Resolves ambiguity *before* code gets written, not after.

**Never assign to it:**
- Writing large volumes of implementation code itself (burns message budget fast and free-tier context windows are the wrong tool for 500-line files — that's OpenCode's job).
- Anything that requires running code, seeing real error output, or iterating against a live environment. Claude Account #1 never sees your terminal.

### Claude Account #2 — **The Reviewer / QA**
**Responsible for:**
- Reviews code OpenCode/DeepSeek produced *against the spec Account #1 wrote* — not against its own opinion of good architecture. Its job is "does this match the spec and not violate a Hard Constraint," not "how would I have designed this."
- Writes test cases and edge cases for a given module (e.g. "what should the extractor do if `us-gaap:StockholdersEquity` is missing").
- Flags scope creep, unnecessary abstraction, or premature optimization in generated code.
- Second set of eyes specifically on anything DeepSeek wrote that touches money (ratio math, unit/scale handling) — this is the account that catches the "confidently wrong number" failure mode before it ships.

**Never assign to it:**
- Redesigning anything Account #1 already decided. If Account #2 disagrees with an architectural call, that disagreement goes back to you, and you decide whether to reopen it with Account #1 — Account #2 doesn't unilaterally steer the project.
- Writing original feature code. It reviews and tests; it doesn't author.

### OpenCode + DeepSeek — **The Implementer**
**Responsible for:**
- All actual file writing: parsers, chunkers, FastAPI routes, React components, SQL migrations — anything that becomes a committed file.
- Local iteration: running the code, reading real stack traces, fixing its own syntax/runtime errors without needing a Claude round-trip for every small bug.
- Boilerplate at scale (Pydantic models, repetitive CRUD endpoints, test scaffolding).

**Never assign to it:**
- Architectural decisions ("should we use hybrid retrieval or vector-only" — that's already decided and logged; OpenCode implements the decision, it doesn't make one).
- Anything where a wrong default would silently violate a Hard Constraint and might not be caught by a quick review (e.g. don't let it "helpfully" add a fallback that estimates a ratio when data is missing — it must show "Insufficient data" per spec, and Account #2 checks this explicitly).

### How the three work together, per task
```
1. You + Claude #1 (chat) ──► produces a written spec + exact OpenCode prompt
2. You paste that prompt into OpenCode ──► DeepSeek generates/edits code locally
3. You run it locally, OpenCode iterates on errors with you until it runs
4. You paste the resulting diff/file into Claude #2 (chat) ──► review pass
5. Fix anything Account #2 flags (back to OpenCode for small fixes,
   back to Account #1 only if the fix implies a spec change)
6. You update DEV_LOG.md yourself (see Part 6) with a 3-5 line summary
7. Next session starts by pasting the updated memory files into whichever
   Claude account you're using
```

### Context transfer — the core rule
**The repo's markdown files are the single source of truth, not either Claude account's chat history.** Neither Claude account has memory of the other, and free-tier sessions don't persist indefinitely either. Every session, in either account, starts with you pasting (or, if using Claude Projects, having already uploaded) the current ARCHITECTURE.md / TECH_DECISIONS.md / PROJECT_MEMORY.md / DECISION_LOG.md / DEV_LOG.md. OpenCode doesn't have this problem the same way — it reads your actual repo files directly every session, so keeping specs and decisions *in the repo as files* (not just in Claude chat transcripts) is what makes OpenCode reliably see the same context Claude does.

### Avoiding duplicated work
- **One owner per artifact.** Architecture docs → Account #1 only. Code → OpenCode only. Test review → Account #2 only. If you ever find yourself asking both Claude accounts the same design question, that's a signal you've blurred the boundary — stop and route it back to Account #1 only.
- **Specs are versioned, not re-derived.** Account #1 writes a spec once per task; OpenCode implements against that spec; Account #2 reviews against that same spec. Nobody re-invents the spec mid-stream.

---

## PART 2 — PROJECT IMPLEMENTATION ROADMAP

### Phase 0 — Preparation
- **Objective:** Repo, environment, and memory-file system exist and are reproducible.
- **Deliverables:** Git repo initialized; Python/Node environments working locally; Supabase project provisioned (free tier); `.env.example` committed (real `.env` gitignored).
- **Files to create:** `README.md`, `.env.example`, `.gitignore`, `backend/requirements.txt`, `frontend/package.json`, `docs/ARCHITECTURE.md`, `docs/TECH_DECISIONS.md`, `docs/PROJECT_MEMORY.md`, `docs/DECISION_LOG.md`, `docs/DEV_LOG.md`.
- **Expected outputs:** `uvicorn` boots a hello-world FastAPI app; `npm run dev` boots a blank Vite+React app; a `SELECT 1` succeeds against Supabase from a local script.
- **Completion criteria:** All four "hello world" checks above pass, and the memory-file folder structure from Part 6 exists in the repo.

### Phase 1 — Data Acquisition
- **Objective:** Reliable, rate-limited, cached access to SEC EDGAR (submissions, XBRL company facts, and raw filing documents).
- **Deliverables:** A small `edgar_client.py` module: CIK resolver, submissions fetcher, company-facts fetcher, raw-filing fetcher — all throttled and User-Agent compliant.
- **Files to create:** `backend/edgar/client.py`, `backend/edgar/models.py` (Pydantic response models), `backend/edgar/cache.py` (local/Supabase caching of raw responses), `tests/test_edgar_client.py`.
- **Expected outputs:** Running the client against Apple's CIK (0000320193) returns submissions JSON, company-facts JSON, and downloads the same `.htm` filing you already inspected manually.
- **Completion criteria:** Fetching Apple's FY2025 10-K programmatically reproduces byte-identical content to the manually-downloaded ZIP's `aapl-20250927.htm`; rate limiting verified (no 403s across a repeated test run).

### Phase 2 — Ingestion Pipeline (narrative/Docling side)
- **Objective:** One filing parsed, chunked, tagged with mandatory metadata, embedded, and stored — Workload A's foundation.
- **Deliverables:** `parser.py` (Docling), `chunker.py` (3-level hierarchical), `metadata.py` (tagger), embedding call, Supabase writes to `documents` + `chunks`.
- **Files to create:** `backend/ingestion/parser.py`, `backend/ingestion/chunker.py`, `backend/ingestion/metadata.py`, `backend/ingestion/embed.py`, `backend/db/schema.sql`, `tests/test_chunker.py`.
- **Expected outputs:** Apple's 10-K produces N chunks in Supabase, each with all mandatory metadata fields populated, tables preserved atomically (verified by manual spot-check of 5-10 chunks).
- **Completion criteria:** Matches your existing Phase 1 gate exactly — one 10-K ingested end-to-end, section boundaries and table preservation verified by manual inspection.

### Phase 3 — Structured Financial Pipeline (XBRL — see Part 3 for detail)
- **Objective:** `structured_financials` populated from XBRL company-facts, not PDF table extraction.
- **Deliverables:** `xbrl_normalizer.py` (concept-mapping + fact normalization), `reconciliation.py` (calculation-linkbase-style cross-checks), Supabase writes to `structured_financials`.
- **Files to create:** `backend/xbrl/normalizer.py`, `backend/xbrl/concept_map.py`, `backend/xbrl/reconciliation.py`, `backend/extractor_fallback.py` (Docling-based, demoted to fallback only), `tests/test_xbrl_normalizer.py`.
- **Expected outputs:** All six dashboard ratios' input line items populated for Apple's FY2025 10-K with correct values, correct scale applied, reconciliation checks passing.
- **Completion criteria:** All six ratios (Gross Margin, Net Margin, ROE, D/E, Current Ratio, P/E) computable from stored data and match Apple's publicly reported figures within rounding.

### Phase 4 — RAG Pipeline (minimal path first)
- **Objective:** A working, demoable answer to a document question — deliberately the *minimal* 3-node version (Classify → Retrieve/Generate → Refuse) before the full 8-node graph, per the earlier review's sequencing recommendation.
- **Deliverables:** BM25 + pgvector hybrid retrieval with RRF merge; a single generation call with citation enforcement; a basic refusal path.
- **Files to create:** `backend/rag/retrieval.py`, `backend/rag/generation.py`, `backend/rag/refusal.py`, `backend/rag/config.yaml` (versioned prompts).
- **Expected outputs:** Asking "What was Apple's total revenue in fiscal 2025?" returns a cited, correct answer; asking something the filing doesn't cover returns an explicit refusal.
- **Completion criteria:** 10 hand-picked test questions (mix of factual, table-based, and unanswerable) all behave correctly without the reranker/HyDE/retry machinery yet.

### Phase 5 — LangGraph Integration (full 8-node)
- **Objective:** Layer in Query Rewriter/HyDE, Reranker, Hallucination Guard, and Retry Logic around the already-working Phase 4 core, per your existing topology.
- **Deliverables:** Full `StateGraph` with all 8 nodes wired, conditional routing tested.
- **Files to create:** `backend/graph/state.py`, `backend/graph/nodes/*.py` (one file per node), `backend/graph/build_graph.py`, `tests/test_graph_nodes.py` (each node tested in isolation, per your own risk log).
- **Expected outputs:** Same 10 test questions from Phase 4, now routed through the full graph, with measurably improved precision on the table-based questions (reranker's specific value-add).
- **Completion criteria:** All 8 nodes individually unit-tested; retry cap of 2 verified not to loop; end-to-end latency measured and logged (expectation-setting, not a hard gate).

### Phase 6 — Frontend
- **Objective:** Three-panel React UI (Upload, Chat, Dashboard) talking to the FastAPI backend, including SSE streaming.
- **Deliverables:** Working upload-progress panel, streaming chat panel, static dashboard panel reading only `structured_financials`.
- **Files to create:** `frontend/src/panels/UploadPanel.tsx`, `ChatPanel.tsx`, `DashboardPanel.tsx`, `frontend/src/api/client.ts`, `frontend/src/hooks/useSSE.ts`.
- **Expected outputs:** A recruiter can upload nothing (pre-seeded with Apple's filing for demo purposes), ask a question, watch tokens stream in with citations, and see the six ratios on the dashboard.
- **Completion criteria:** All three panels functional together in one running session without manual backend restarts.

### Phase 7 — Evaluation
- **Objective:** RAGAS scoring + a golden test set + a CI regression gate — the piece most likely to get rushed (see Part 9).
- **Deliverables:** A ~20-30 question golden set spanning factual/table/narrative/unanswerable/adversarial categories; RAGAS scoring script; GitHub Actions workflow.
- **Files to create:** `eval/golden_set.jsonl`, `eval/run_ragas.py`, `.github/workflows/eval.yml`.
- **Completion criteria:** CI runs on every PR, fails below 0.85 faithfulness, and you've manually spot-checked at least 10 of the 20-30 golden answers yourself (per the earlier review's RAGAS-validity caveat — don't trust the metric blind).

### Phase 8 — Deployment
- **Objective:** Live, recruiter-clickable URL.
- **Deliverables:** Vercel frontend deploy, Railway backend deploy, Supabase production config, environment variables wired, a pre-seeded demo filing so recruiters don't have to upload anything themselves.
- **Files to create:** `vercel.json` (if needed), `railway.toml`/`Procfile`, `docs/DEPLOYMENT.md`.
- **Completion criteria:** A cold, unauthenticated visit to the deployed URL loads the dashboard and chat for the pre-seeded filing within a few seconds, end to end, from a device you didn't develop on.

---

## PART 3 — XBRL INTEGRATION

### Where it fits
Entirely inside **Phase 3**. Nothing before or after Phase 3 changes shape — Phase 2 (Docling/chunking) is untouched, Phase 4 onward (RAG, LangGraph, frontend, eval, deployment) consume `chunks` and `structured_financials` exactly as already designed, unaware of *how* those tables got populated.

### What gets replaced
- `extractor.py`'s role as the **primary** path for `structured_financials` is replaced by `xbrl/normalizer.py` reading SEC's Company Facts API.
- The mental model "structured extraction = parse PDF tables" is replaced by "structured extraction = fetch + normalize XBRL, fall back to PDF parsing only for concepts XBRL doesn't cover."

### What remains unchanged
- Docling, the 3-level chunker, and the metadata tagger — all unchanged, still doing exactly what Phase 2 already specifies, still feeding `chunks` for RAG.
- The `structured_financials` table's core purpose and its "never joined with `chunks`" rule (AD-007) — unchanged.
- LangGraph topology, retrieval, reranking, evaluation, deployment — all untouched, as established in the prior review.
- `extractor.py` itself doesn't disappear — it's kept, demoted to a fallback invoked only when a required concept has no XBRL tag.

### Implementation order (inside Phase 3)
1. `edgar_client.py` (already built in Phase 1) fetches Company Facts JSON for the target CIK.
2. `concept_map.py` — a small static dictionary mapping your ~15-20 required `us-gaap:*` concepts to your six ratios' inputs. Build and hand-verify this against Apple's actual data first (you already have ground truth from the manual ZIP inspection).
3. `normalizer.py` — walks the Company Facts JSON, applies the concept map, resolves the most recent 10-K period, writes rows to `structured_financials` with `source='xbrl_companyfacts'`.
4. `reconciliation.py` — cross-checks `AssetsCurrent + AssetsNoncurrent = Assets` and `Liabilities + StockholdersEquity = Assets` (the two your six ratios actually depend on); flags `reconciled=FALSE` on mismatch rather than silently proceeding.
5. `extractor_fallback.py` — only invoked if a required concept is missing from the normalizer's output; logs which concept and which company triggered the fallback, so you can see empirically how often this path actually fires.

### Minimal viable XBRL pipeline (build this first, expand later)
```python
# backend/xbrl/normalizer.py — MVP version, Apple-only, hardcoded CIK
CIK = "0000320193"
REQUIRED_CONCEPTS = [
    "Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent",
    "StockholdersEquity", "NetIncomeLoss",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "CostOfGoodsAndServicesSold",  # gross margin input
    "EarningsPerShareDiluted",
]
# 1. fetch companyfacts JSON via edgar_client
# 2. for each concept in REQUIRED_CONCEPTS: pull most recent 10-K "FY" fact
# 3. insert one row per concept into structured_financials
# 4. run reconciliation.py checks
# 5. print a human-readable table for manual verification against
#    the numbers you already saw in the manually-inspected ZIP
```
This MVP deliberately skips multi-company support, historical time series, and the fallback path — get one company's six ratios correct and verified first, then generalize.

### A vs. B: manual download vs. automatic API pull

**Recommendation: both, at different stages, not a single either/or choice.**
- **During Phase 3 development (now):** keep using the manually-downloaded ZIP you already have. It's a known, inspected, ground-truth dataset — ideal for writing and debugging `normalizer.py` and `reconciliation.py` against values you've already hand-verified, without burning EDGAR rate-limit budget or dealing with network flakiness while iterating.
- **For anything beyond the one Apple filing (Phase 3 completion onward, and definitely by Phase 8 deployment):** switch to Option B, automatic pulls via `edgar_client.py`. A recruiter-facing deployed app cannot depend on you manually downloading a ZIP every time someone wants a different company's filing — that's not a "production-grade" story, and it contradicts your own stated goal.
- **Practical sequencing:** write `normalizer.py` against the local ZIP file first (fast iteration, no network), then swap the input source to `edgar_client.py`'s live fetch once the normalization logic is verified correct — the parsing logic itself doesn't change, only where the bytes come from.

---

## PART 4 — CLAUDE PROMPT STRATEGY

### System Prompt — Claude Account #1 (The Architect)
```
You are the sole architecture owner for the "Ask My Filings" project — a
financial-document RAG system with a hard separation between deterministic
analytics (structured_financials) and probabilistic retrieval (chunks),
never joined at query time.

Your ONLY outputs in this role are:
1. Written specs (file names, function signatures, inputs/outputs,
   acceptance criteria) precise enough for a separate coding tool to
   implement without further clarification.
2. Exact prompts to hand to that coding tool.
3. Updates to the project's memory files (ARCHITECTURE.md, TECH_DECISIONS.md,
   PROJECT_MEMORY.md, DECISION_LOG.md) when a real decision is made or changed.

Hard rules:
- Never propose replacing a locked technology choice (Docling, FastAPI,
  LangGraph, Supabase+pgvector, hybrid BM25+vector retrieval, XBRL-primary
  structured extraction) without the person explicitly asking you to
  reconsider it, and even then, log it as a Conflict Resolution entry with
  a documented reason — never silently substitute.
- Never write large blocks of implementation code yourself. If a task needs
  more than ~15 lines of illustrative code, write the spec instead and
  route it to the coding tool.
- Every Hard Constraint (never guess a financial number; explicit refusal
  over hallucination; tables never flattened; mandatory chunk metadata;
  retry hard-capped at 2) is non-negotiable. If a task risks touching one,
  say so explicitly in the spec and flag it for the review account.
- If information is missing or a request is ambiguous, state the
  assumption you're making and proceed — don't block on a clarifying
  question unless proceeding would clearly go the wrong direction.
- Keep specs and prompts short enough to paste directly into a coding tool
  without truncation. Prefer bullet points and code signatures over prose.
- At the end of every session, produce a 3-5 line DEV_LOG.md entry:
  what was decided, what was built, what's next.
```

### System Prompt — Claude Account #2 (The Reviewer / QA)
```
You are the code reviewer and QA function for the "Ask My Filings" project.
You review code against a written spec provided to you — you do not
redesign, and you do not invent your own architectural preferences.

Your ONLY outputs in this role are:
1. A pass/fail assessment against the specific spec you were given.
2. A list of concrete bugs, edge cases, or Hard Constraint violations,
   each with a one-line fix suggestion.
3. Test cases (as code or as a described scenario) for the module under
   review, especially edge cases involving missing data, malformed input,
   or unit/scale confusion.

Hard rules:
- Do not suggest architectural changes. If you believe the architecture
  itself has a problem, say so once, clearly labeled as "architecture
  concern, not a code defect," and stop there — the person decides whether
  to route it back to the Architect account.
- Treat any code that computes a financial ratio, extracts a financial
  value, or decides between "return the number" vs. "return Insufficient
  data" as highest-priority review material. Check explicitly: correct
  concept/tag used, correct scale/decimals applied, correct period
  resolved, and a defined behavior when the value is missing.
- Do not approve code that silently estimates, interpolates, or defaults
  a financial value that should be "Insufficient data" instead.
- Flag over-engineering as readily as you flag bugs: unnecessary
  abstraction layers, premature generalization, or scope beyond what the
  spec asked for are defects too, not virtues.
- Keep reviews concrete and actionable — no generic "consider improving
  readability" notes without a specific line and a specific suggestion.
```

---

## PART 5 — OPENCODE STRATEGY

General pattern per phase: Claude #1's spec becomes the OpenCode prompt almost verbatim, with one addition — always end the OpenCode prompt with "do not modify files outside `<list>`" to stop DeepSeek from opportunistically "fixing" unrelated code.

| Phase | OpenCode prompt shape | Delegate to OpenCode | Keep under human review | Auto-generate freely | Never auto-generate |
|---|---|---|---|---|---|
| **0 Prep** | "Scaffold a FastAPI backend and Vite+React frontend per this file tree: [tree]. Don't add dependencies beyond [list]." | Boilerplate scaffolding, `requirements.txt`/`package.json` | Nothing yet — low risk | Folder structure, config stubs | `.env` with real secrets |
| **1 Data Acquisition** | "Implement `edgar_client.py` per this spec: [spec]. Rate-limit to 8 req/sec, real User-Agent header, exponential backoff on 403/429." | HTTP client code, retry/backoff logic | Rate-limit correctness (test it actually throttles) | Pydantic response models | The User-Agent contact string (use a real one you control) |
| **2 Ingestion** | "Implement `chunker.py` per this 3-level spec: [spec]. Unit tests for table-splitting behavior." | Docling integration boilerplate, chunk-splitting logic | Manual spot-check of 5-10 real chunks against the actual filing | Metadata tagger field population | Silent fallback behavior for malformed tables — must raise/log, not guess |
| **3 XBRL** | "Implement `normalizer.py` per this concept map: [map]. Hardcode Apple CIK for now." | JSON walking, normalization code | The concept map itself (verify each mapping against real values) | Reconciliation-check arithmetic | Any "best guess" fallback when a concept is missing — must mark Insufficient data |
| **4 RAG core** | "Implement retrieval.py: BM25 + pgvector, RRF merge, per this spec." | Retrieval/merge code, prompt template file structure | The actual prompts in `config.yaml` (read every word — these drive hallucination risk) | SQL query building | The refusal-threshold logic without a human decision on where the line sits |
| **5 LangGraph** | "Implement one node at a time: [node spec]. Unit test each node before wiring into the graph." | Individual node implementations | The conditional-edge routing logic (your own docs flag this as bug-prone) | Node-level unit tests | The retry-cap value (must stay at 2 per Hard Constraint, don't let it get "optimized") |
| **6 Frontend** | "Implement ChatPanel.tsx with SSE streaming per this component spec." | React component code, styling, SSE plumbing | Citation rendering correctness (does it show real doc/section/page) | CSS/layout | Anything that silently swallows a backend error instead of showing it |
| **7 Evaluation** | "Write `run_ragas.py` per this spec against `golden_set.jsonl`." | RAGAS scoring script, CI YAML | The golden set questions/answers themselves — write and verify these yourself with Claude #1's help, don't let DeepSeek invent test questions | CI workflow boilerplate | The golden set's "correct" answers — those must be human/Claude-verified against real filing content |
| **8 Deployment** | "Write deployment config per this checklist: [checklist]." | Config file boilerplate | Environment variable wiring (secrets) | `Procfile`/`railway.toml` structure | Anything that embeds a real secret/key in a committed file |

**Cross-cutting rule for all phases:** never let OpenCode/DeepSeek generate the *values* that go into a Hard Constraint decision (the retry cap, the faithfulness threshold, the concept map, the golden set answers) — it can generate the *code structure* that uses those values, but the values themselves come from your spec, verified against real data.

---

## PART 6 — SESSION MANAGEMENT

### Files needed for continuity

| File | Owner | Purpose | Updated when |
|---|---|---|---|
| `docs/ARCHITECTURE.md` | Claude #1 | System design, data flow, schema — as already exists | Only on a real architecture change, logged as a conflict-resolution entry |
| `docs/TECH_DECISIONS.md` | Claude #1 | Locked tech choices + reasoning — as already exists | Only when a locked decision is formally reopened |
| `docs/PROJECT_MEMORY.md` | Claude #1 | Overall project state snapshot — as already exists | End of each phase, not each session (too noisy otherwise) |
| `docs/DECISION_LOG.md` | Claude #1 | **New.** One-line-per-decision running log, most recent first, with date and rationale | Every time a non-trivial decision is made, including small ones ARCHITECTURE.md is too heavy to log |
| `docs/DEV_LOG.md` | You (from Claude #1's session summary) | **New.** Chronological session-by-session log: what was attempted, what worked, what broke, what's next | End of every session, no exceptions |
| `docs/prompts/` | You | **New.** Saved copies of every non-trivial OpenCode prompt that worked, so you're not re-deriving them | Whenever a prompt produces good output worth reusing |
| `docs/golden_set.jsonl` | Claude #1 + You | Evaluation ground truth | Phase 7, then rarely |
| `docs/xbrl_concept_map.md` | Claude #1 | Human-readable version of `concept_map.py`, with the source values you hand-verified | Phase 3, updated if you add companies/concepts |

### Exact folder structure
```
ask-my-filings/
├── README.md
├── .env.example
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── main.py
│   ├── edgar/
│   │   ├── client.py
│   │   ├── models.py
│   │   └── cache.py
│   ├── ingestion/
│   │   ├── parser.py
│   │   ├── chunker.py
│   │   ├── metadata.py
│   │   └── embed.py
│   ├── xbrl/
│   │   ├── normalizer.py
│   │   ├── concept_map.py
│   │   └── reconciliation.py
│   ├── extractor_fallback.py
│   ├── graph/
│   │   ├── state.py
│   │   ├── build_graph.py
│   │   └── nodes/
│   │       ├── classifier.py
│   │       ├── rewriter.py
│   │       ├── retrieval.py
│   │       ├── reranker.py
│   │       ├── generation.py
│   │       ├── hallucination_guard.py
│   │       ├── refusal.py
│   │       └── retry.py
│   ├── rag/
│   │   └── config.yaml
│   ├── db/
│   │   └── schema.sql
│   └── tests/
│       ├── test_edgar_client.py
│       ├── test_chunker.py
│       ├── test_xbrl_normalizer.py
│       └── test_graph_nodes.py
├── frontend/
│   ├── package.json
│   └── src/
│       ├── panels/
│       │   ├── UploadPanel.tsx
│       │   ├── ChatPanel.tsx
│       │   └── DashboardPanel.tsx
│       ├── api/
│       │   └── client.ts
│       └── hooks/
│           └── useSSE.ts
├── eval/
│   ├── golden_set.jsonl
│   └── run_ragas.py
├── .github/
│   └── workflows/
│       └── eval.yml
└── docs/
    ├── ARCHITECTURE.md
    ├── TECH_DECISIONS.md
    ├── PROJECT_MEMORY.md
    ├── DECISION_LOG.md
    ├── DEV_LOG.md
    ├── DEPLOYMENT.md
    ├── xbrl_concept_map.md
    └── prompts/
        └── (saved OpenCode prompts, one .md per module)
```

### How to avoid context loss, concretely
- **Never rely on either Claude account's chat history surviving.** Assume every session starts cold. Paste the current `PROJECT_MEMORY.md` + `DECISION_LOG.md` + last 2-3 `DEV_LOG.md` entries at the start of every Claude Account #1 or #2 session (this is a 30-second copy-paste, not a burden).
- **OpenCode doesn't need this pasting** because it reads the repo directly — but only if `docs/` is actually inside the repo it has access to, not a separate folder on your machine.
- **DEV_LOG.md entries are mandatory, not optional**, even for a 20-minute session that didn't finish anything — "attempted X, blocked on Y, next session start with Z" is exactly the information that prevents re-deriving the same debugging path twice.

---

## PART 7 — IMPLEMENTATION SCHEDULE (20 sessions, 2-4h each)

Realistic assumption: limited full-stack experience means sessions 1-6 will run slower than the phase roadmap alone suggests — schedule reflects that by front-loading extra sessions on ingestion/XBRL (the parts with the most new concepts) and compressing frontend (a smaller, more mechanical phase once the backend works).

| # | Goal | Tasks | Expected output | Validation checkpoint |
|---|---|---|---|---|
| 1 | Repo + environment | Phase 0 scaffolding via OpenCode | Backend/frontend both boot locally | Both hello-world checks pass |
| 2 | Supabase + schema | Write `schema.sql`, provision Supabase, connect | Tables exist, connection verified from Python | `SELECT * FROM documents` returns empty but no error |
| 3 | EDGAR client (part 1) | `client.py` CIK resolution + submissions fetch | Apple CIK resolves, submissions JSON printed | Manual diff against known Apple CIK (0000320193) |
| 4 | EDGAR client (part 2) | Company-facts + raw filing fetch, rate limiting, caching | Full client working end to end | Fetched `.htm` matches the manually-inspected ZIP's file |
| 5 | Docling parser | `parser.py` against the Apple filing | Structured element tree from Docling | Spot-check 3 sections (Item 1, Item 7, a financial statement) parse correctly |
| 6 | Chunker (part 1) | 3-level hierarchical chunker, narrative chunks only | Narrative chunks with correct boundaries | 5 chunks manually verified against source text |
| 7 | Chunker (part 2) | Table-aware chunking, sub-table splitting | Tables preserved atomically | A large table (e.g. balance sheet) verified not flattened |
| 8 | Metadata + embeddings | `metadata.py`, embedding calls, writes to `chunks` | Populated `chunks` table, all metadata fields non-null | Query `chunks` for one company/fiscal_year filter, get correct rows |
| 9 | **Phase 1 gate check** | Full re-run of ingestion end to end on Apple's 10-K | Complete ingested filing in Supabase | Matches your documented Phase 1 gate criteria exactly |
| 10 | XBRL normalizer (part 1) | `concept_map.py` + basic `normalizer.py` against local ZIP | Six ratios' raw inputs extracted and printed | Values match what you hand-verified in the prior manual review |
| 11 | XBRL normalizer (part 2) | Reconciliation checks, write to `structured_financials`, swap source to live API fetch | Populated `structured_financials`, reconciliation passing | `Assets = AssetsCurrent + AssetsNoncurrent` check passes for Apple |
| 12 | RAG core (part 1) | Hybrid retrieval (BM25 + pgvector + RRF) | Retrieval returns relevant chunks for test queries | 3 test queries manually judged for relevance |
| 13 | RAG core (part 2) | Generation with citation enforcement, `config.yaml` prompts | Cited answers to factual questions | 5 factual questions answered correctly with citations |
| 14 | Refusal path | Explicit refusal node, wire into minimal 3-node graph | Unanswerable questions correctly refused | 3 out-of-scope questions correctly refused, no hallucination |
| 15 | **Phase 4 gate check** | Full 10-question test set against the minimal pipeline | All 10 behave correctly | Documented pass/fail per question |
| 16 | LangGraph expansion (part 1) | Reranker + HyDE nodes, unit-tested individually | Two new nodes passing isolated tests | Reranker measurably improves a table-based test question |
| 17 | LangGraph expansion (part 2) | Hallucination guard + retry logic, full graph wired | Complete 8-node graph running | Retry cap verified not to loop; same 10-question set re-run |
| 18 | Frontend (part 1) | Dashboard panel + upload panel | Static dashboard shows six ratios | Numbers match `structured_financials` exactly |
| 19 | Frontend (part 2) | Chat panel with SSE streaming, wire all three panels together | Full 3-panel UI functional locally | End-to-end demo runs without manual restarts |
| 20 | Evaluation + deploy prep | Golden set (start small, 10-15 questions), RAGAS script, deployment checklist | CI running, deployment config drafted | At least a partial deploy reachable at a public URL, even if evaluation set isn't fully at 20-30 questions yet |

**Realistic framing:** 20 sessions gets you through Phase 7 partially and into the start of Phase 8, not a fully polished, fully-evaluated, fully-deployed system — see Part 9 for why, and don't be surprised if sessions 18-20 slip into a 21st-25th session range.

---

## PART 8 — RISK ANALYSIS

| Risk | Category | Probability | Impact | Mitigation |
|---|---|---|---|---|
| Docling mis-parses a real 10-K table (merged cells, multi-page) | Technical | Medium-High | Medium (Workload A only, since XBRL now covers Workload B) | Spot-check chunks manually every ingestion session; XBRL hybrid already de-risked the higher-stakes half |
| LangGraph conditional-edge bug causes an infinite or incorrect route | Technical | Medium | Medium | Unit-test every node in isolation *before* wiring the graph (Session 16-17), exactly as your own docs already flag |
| DeepSeek generates plausible-but-wrong code that passes a shallow glance | OpenCode/DeepSeek | Medium-High | High if it touches ratio math | Claude Account #2 review is mandatory, not optional, for anything in `xbrl/` or `rag/generation.py` |
| DeepSeek "helpfully" refactors files outside the requested scope | OpenCode/DeepSeek | Medium | Low-Medium (wasted time, possible regressions) | Always scope OpenCode prompts to an explicit file list; diff-review before accepting |
| Claude Free message/session limits interrupt a debugging flow mid-task | Claude Free limitations | High | Low-Medium (annoying, not fatal) | Keep DEV_LOG.md current enough that resuming costs 2 minutes, not 20; use Account #2 for lighter review tasks so Account #1's budget lasts for design work |
| Context drift between the two Claude accounts (Account #2 starts making architecture calls) | Workflow | Medium | Medium | The system prompts in Part 4 explicitly forbid this; you as the human are the actual enforcement mechanism — watch for it |
| DECISION_LOG.md / DEV_LOG.md updates get skipped under time pressure | Context-management | High | High (compounds every skipped session) | Make it the very last, non-negotiable step of every session before closing the laptop — a 3-line entry, not a essay |
| Golden set for evaluation gets built carelessly/rushed | Workflow | Medium-High | High (undermines your own stated differentiator) | Build it incrementally from Session 5 onward (save good test questions as you go) rather than inventing 20-30 questions cold in Session 20 |
| Supabase free-tier project pauses from inactivity between sessions | Technical | Medium | Low (just a wake-up delay) | Known and acceptable per your own docs; don't treat as a surprise |
| SEC EDGAR rate-limit block (403) during automated testing | Technical | Low-Medium | Low | `edgar_client.py` throttling + backoff built and tested in Session 3-4, before it's load-bearing |
| Frontend (3-panel React + SSE) takes longer than scheduled for a non-frontend-heavy developer | Workflow | High | Medium | Schedule already allocates 2 full sessions (18-19); be willing to take a 3rd if needed rather than cutting scope on citation rendering |
| Scope creep: adding multi-company support before single-company works end to end | Workflow | Medium | Medium-High | Explicitly deferred in the roadmap (Session 9's gate is single-filing only) — resist the urge to generalize early |

---

## PART 9 — CRITICAL REVIEW (brutally realistic)

**Hidden bottlenecks:**
- **The three-tool handoff itself is overhead you're underpricing.** Every task now costs: write spec (Account #1) → paste into OpenCode → iterate locally → paste result into Account #2 → fix flagged issues → update logs. That's 4-5 context switches per task, each with its own small friction (copy-pasting large files, re-explaining state). For a solo MBA-background developer with limited full-stack experience, this coordination overhead is realistically 20-30% of total session time, not free.
- **Claude Free's message/session caps will bite hardest exactly when you need them least — mid-debugging.** The schedule assumes clean session boundaries; real debugging doesn't respect them. Expect some sessions to end with "ran out of Account #1 budget mid-spec" rather than at a clean stopping point.
- **The evaluation phase (Phase 7) is the single most likely piece to get quietly cut or rushed**, because by session 18-20 you'll be tired, the frontend will feel more "done" and satisfying to polish than writing 20-30 careful test questions, and nothing forces you to do it well except your own discipline. This is exactly the failure mode the original viability review flagged as a portfolio risk ("no evaluation infra = indistinguishable from a tutorial clone") — worth protecting deliberately, not left to whatever energy is left at the end.

**Unnecessary complexity, given your actual constraints:**
- **Running two separate Claude Free accounts for architecture vs. review is a reasonable division of labor, but don't over-formalize it.** For small, obviously-correct changes (a one-line config tweak, a typo fix), routing through the full Account #1 → OpenCode → Account #2 pipeline is wasted ceremony. Use judgment: reserve the two-account split for anything touching a Hard Constraint or a genuine design choice, and just fix small things directly.
- **The eval CI gate (GitHub Actions on every PR) is arguably premature at solo-developer, pre-code-complete scale.** It's good signal for a finished portfolio, but running it as a blocking gate *during* active development (when you're still building Phases 4-6) will mostly generate noisy failures on unfinished work. Consider building the RAGAS script in Phase 7 but not wiring it as a hard PR-blocking gate until closer to Phase 8, so it doesn't become friction during the phases that most need fast iteration.

**Where effort is being underestimated:**
- **20 sessions × 2-4 hours (40-80 hours total) for the full scope described (8-node LangGraph, hybrid retrieval, reranking, XBRL, 3-panel SSE frontend, RAGAS+CI, two-platform deployment) is optimistic for someone who has described themselves as having limited full-stack experience.** The schedule in Part 7 is paced reasonably, but it assumes each session lands roughly on-target; in practice, expect Sessions 5-9 (ingestion/Docling) and 16-17 (LangGraph expansion) to be the ones that run long, because they involve genuinely new debugging surfaces (structure-aware parsing quirks, async conditional-edge behavior) that don't have a clean, mechanical fix path the way a schema migration does.
- **Frontend is very commonly underestimated by developers who came from analytics/data backgrounds, not frontend engineering.** SSE streaming state management, citation rendering that stays in sync with streamed tokens, and a dashboard that gracefully shows "Insufficient data" rather than breaking — these are all small individually but add up. Two sessions (18-19) is a reasonable target, but budget mentally for a third before you're actually surprised by it.
- **"Deployed and demoable" (Phase 8) usually reveals problems that don't show up in local development** — CORS issues between Vercel and Railway, environment variable mismatches, Supabase connection pooling under a cold start. This is normal, but it means Session 20 realistically produces "mostly deployed, one or two rough edges," not "fully polished live demo," and that's fine — don't treat it as a plan failure if it takes a 21st session to actually feel recruiter-ready.

**What I'm not saying:** none of this is a reason to cut LangGraph's full topology, the evaluation harness, or the hybrid retrieval stack — the prior review already concluded those are good signal worth keeping. The realistic read is purely about pacing: expect the plan to run closer to 25-28 sessions than a clean 20, concentrated in ingestion and LangGraph, not because anything here is mis-designed, but because those are the phases with the most genuinely new concepts for you specifically to learn while building.
