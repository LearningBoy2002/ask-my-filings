# PROJECT_MEMORY.md — Ask My Filings
**Status:** Pre-implementation (architecture locked, zero code written)
**Last reconciled:** 2026-08-15
**Purpose:** This is the single authoritative memory file for Claude Projects. It supersedes all prior versions of `PROJECT_MEMORY.md` and `ASK_MY_FILINGS_CONTEXT.md`. Where earlier conversations conflict with this file, this file wins.

**Revision note (2026-08-15):** Incorporates the two locked changes from `ask-my-filings-viability-review.md` (AD-012 XBRL-primary structured extraction; LLM decision reopened) and the build-sequencing change from `execution-plan.md` (AD-013 minimal-graph-first LangGraph build). This file, `ARCHITECTURE.md`, and `TECH_DECISIONS.md` together are the ground-truth spec to feed OpenCode/DeepSeek for a from-scratch implementation, per the execution plan's three-tool workflow (Claude Architect / Claude Reviewer / OpenCode Implementer).

---

## 1. PROJECT GOAL

Build **Ask My Filings** — a portfolio-grade, production-minded financial document intelligence system. Users upload SEC filings (10-K, 10-Q, earnings transcripts) and:
- Ask grounded questions and receive citation-backed answers
- Get automatic refusal when evidence is insufficient (never a guess)
- View financial ratios computed deterministically from extracted structured data
- Interact through a live, recruiter-usable, deployed system — not a local-only demo

**This is NOT:** a generic chatbot, a "chat with PDF" wrapper, a tutorial RAG clone, or a system that derives financial ratios from LLM-generated text.

**Builder context:** Fresher, B.Tech CSE + MBA Business Analytics (BITS Pilani), targeting analytics / AI-data science / finance analytics / consulting roles. Build must stay near-zero cost at demo scale (~50 recruiter queries/month; exact target cost depends on the LLM re-evaluation, see Section 6).

---

## 2. TECH STACK (FINAL)

| Layer | Tool |
|---|---|
| Frontend | React + TypeScript + Tailwind CSS + shadcn/ui + Vite |
| Backend | Python + FastAPI + Uvicorn (SSE streaming) |
| Parser (narrative/table chunking) | Docling |
| Structured financial extraction | **XBRL Company Facts API (primary)** via `edgar_client.py` + `xbrl/normalizer.py` + `xbrl/reconciliation.py`; Docling-based `extractor.py` demoted to fallback only (AD-012) |
| Orchestration | LangChain (plumbing) + LangGraph (8-node StateGraph target; built minimal-first, see AD-013) |
| Storage | Supabase (Postgres + pgvector + file storage) |
| Local prototyping only | ChromaDB (never production — ephemeral on cloud restarts) |
| Retrieval | BM25 (keyword) + pgvector (dense) → Reciprocal Rank Fusion → cross-encoder reranking (reranking layered in at Phase 5) |
| Evaluation | RAGAS + Langfuse (tracing) + GitHub Actions CI (non-blocking until Phase 8, see AD-009 note) |
| Deployment | Vercel (frontend) + Railway (backend) + Supabase (data) |
| Embedding model | **Unresolved — open blocker, see Section 6** |
| LLM | **Reopened 2026-08-15 — GPT-4o-mini is mid-retirement, must not be silently defaulted to, see Section 6** |

---

## 3. ARCHITECTURE SUMMARY

```
User → React Frontend (Upload / Chat / Dashboard panels)
     → FastAPI Backend
         ├─ Ingestion Path A (chat): Docling parse → hierarchical chunker
         │             (table-aware) → metadata tagger → embeddings
         │             → Supabase `chunks`
         ├─ Ingestion Path B (dashboard): EDGAR XBRL Company Facts API
         │             → normalizer → reconciliation checks
         │             → Supabase `structured_financials`
         │             (Docling extractor = fallback only, logged when used)
         └─ Query: LangGraph StateGraph
               Phase 4 (build first): Classifier → Retrieve+Generate → Refusal
               Phase 5 (layer in): + HyDE rewrite, + cross-encoder rerank,
               + hallucination guard, + retry (max 2) → hard fallback to refusal
Dashboard reads ONLY from the structured fields table — never from RAG output.
Evaluation: RAGAS + Langfuse trace every node; GitHub Actions CI (blocking
from Phase 8 onward) fails builds if faithfulness < 0.85.
Deployment: Vercel (FE) + Railway (BE, avoids serverless 10s timeout) + Supabase (data).
```

**Two independent workloads, deliberately separated:** (1) open-ended document Q&A via hybrid RAG, and (2) deterministic financial-ratio computation via structured extraction (now XBRL-primary). They never feed into each other.

---

## 4. KEY DECISIONS (Accepted, in force)

| # | Decision | Reasoning (short) |
|---|---|---|
| AD-001 | Docling for narrative/table parsing (chat path) | Preserves tables/headings/hierarchy; naive parsers flatten tables into unreadable text |
| AD-002 | React+TS+Tailwind+shadcn/ui+Vite frontend | Needs 3 simultaneous UI states (upload progress, streaming chat, static dashboard) — Streamlit can't cleanly isolate these |
| AD-003 | Python+FastAPI backend | AI/eval/parsing SDKs are Python-first; FastAPI supports SSE streaming |
| AD-004 | Supabase (Postgres+pgvector) for production storage | Persistent (unlike ChromaDB on cloud restarts); bundles vector search + SQL metadata filters + file storage + auth path in one free-tier service |
| AD-005 | Hybrid retrieval (BM25+vector) + cross-encoder rerank | Vector-only misses exact terms (tickers, "EBITDA," "Item 7"); BM25-only misses semantic intent |
| AD-006 | LangGraph 8-node StateGraph for workflow control (target topology) | Needs conditional routing, retries, and validation gates that bare LangChain chains can't express |
| AD-007 | Financial ratios computed deterministically from structured extraction, never from RAG text | Hard constraint — prevents unit/period-confusion producing confidently-wrong numbers |
| AD-008 | Hierarchical, element-based, table-aware chunking | Outperforms fixed-token chunking on financial Q&A per cited research; tables preserved atomically, never flattened |
| AD-009 | RAGAS + Langfuse + GitHub Actions CI regression gate (non-blocking until Phase 8) | No eval infra = indistinguishable from a tutorial clone; faithfulness ≥0.85 blocks merges once wired as blocking |
| AD-010 | Vercel (frontend) + Railway (backend) deployment | Vercel serverless's 10s timeout breaks multi-call LangGraph pipelines; Railway supports persistent SSE |
| AD-011 | HyDE used conditionally, both at query time (short/ambiguous queries only, Phase 5) and at ingestion time (pre-generated hypothetical questions per chunk, Phase 5) | Bridges the query-vs-answer vector-space gap in formal financial language without adding cost to every query |
| AD-012 *(new)* | `structured_financials` populated primarily from SEC's free XBRL Company Facts API, not PDF table extraction; Docling extractor demoted to logged fallback | Issuer-attested, machine-readable data removes the largest correctness risk from the system's most safety-critical component; directly serves Hard Constraint #1 |
| AD-013 *(new)* | LangGraph built minimal-first: 3-node graph (Classifier → Retrieve+Generate → Refusal) validated in Phase 4, then HyDE/Reranker/Hallucination Guard/Retry layered in as Phase 5 | Gets an end-to-end demoable system alive faster; directly addresses the project's own self-flagged risk that conditional-edge logic is bug-prone and untested in isolation |
| AD-014 *(new)* | Reconciliation validation (`AssetsCurrent + AssetsNoncurrent = Assets`, etc.) is a designed-in Phase 3 requirement, not an optional gap | Directly protects Hard Constraint #1; was previously filed as a lower-priority "open gap," which understated its importance |

---

## 5. CONFLICT RESOLUTION LOG
*(Documented so Claude never reverts to an earlier, superseded choice.)*

### Conflict 1 — Vector storage
**Previous Decision:** Neon (serverless Postgres + pgvector) as the production storage layer, with ChromaDB for local prototyping.
**Updated Decision:** Supabase (Postgres + pgvector + Storage) as the production storage layer. ChromaDB remains local-prototyping-only.
**Reason for Change:** Neon is database-only. Supabase bundles pgvector, file storage for uploaded PDFs, real-time subscriptions, and a row-level-security auth path in one free-tier account — reducing the number of services needed for a recruiter-facing demo. This was a deliberate mid-project pivot, not an oversight.

### Conflict 2 — Frontend framework
**Previous Decision:** Streamlit or Hugging Face Spaces for frontend/demo (stated in the earliest project brief).
**Updated Decision:** React + TypeScript + Tailwind CSS + shadcn/ui + Vite.
**Reason for Change:** The required UI has three simultaneously-active states — file upload with progress, token-streaming chat, and a static analytics dashboard. Streamlit re-runs the entire script per interaction, making it fight this pattern (ratio cards would recompute on every chat message). React with shadcn/ui component templates ships the required split-pane layout faster and signals full-stack production thinking to recruiters.

### Conflict 3 — Document parser
**Previous Decision:** PyMuPDF (implied default / not yet challenged in earliest brief).
**Updated Decision:** Docling.
**Reason for Change:** Head-to-head comparison research cited ~94% table-structure accuracy for Docling vs. ~45% for PyMuPDF on a 10-K-style document. Financial filings live or die on table fidelity for the retrieval workload, so this was not a close call. (See Conflict 5 for the separate decision on structured-extraction sourcing.)

### Conflict 4 — Deployment target for frontend/demo
**Previous Decision:** Streamlit / Hugging Face Spaces (earliest brief).
**Updated Decision:** Vercel (frontend) + Railway (backend) + Supabase (data).
**Reason for Change:** Follows directly from Conflict 2 (frontend is React, not Streamlit) and from AD-010 (Vercel serverless timeout incompatible with LangGraph backend calls). HF Spaces also carries the same ephemeral-storage problem as ChromaDB, ruled out for the same reason.

### Conflict 5 — Structured financials data source *(new, 2026-08-15)*
**Previous Decision:** `structured_financials` populated exclusively via a custom Docling-based PDF table extractor.
**Updated Decision:** SEC XBRL Company Facts API as the primary source (AD-012); Docling extraction retained only as a logged fallback for concepts missing from a filer's XBRL data.
**Reason for Change:** A senior-architect viability review identified this as the single highest-leverage pre-code change available: XBRL data is free, issuer-attested, and machine-readable, removing the largest correctness risk from the project's most safety-critical component (financial ratios). Additive change — new ingestion branch, three new columns on `structured_financials` (`source`, `concept_tag`, `reconciled`), no disruption to Docling's continued role in narrative/table chunking for chat.

### Conflict 6 — LLM lock status *(new, 2026-08-15)*
**Previous Decision:** GPT-4o-mini referenced as an effectively-locked budget default in some project-instruction contexts, despite being listed as unresolved in this file's own Section 6.
**Updated Decision:** Formally reopened. Must be evaluated head-to-head against current alternatives before Phase 4 (RAG generation) work begins.
**Reason for Change:** GPT-4o-mini is actively being retired across OpenAI's 2026 product surfaces (ChatGPT access to GPT-4o retired Feb 13, 2026; Azure Foundry gpt-4o-mini retirement date Mar 31, 2026). Building tuned prompts and evals around a model mid-retirement is avoidable rework — cheap to fix now (zero code exists), expensive later.

---

## 6. OPEN ITEMS — NOT YET DECIDED (do not treat as resolved)

1. **Embedding model** — candidates on the table: `text-embedding-3-small` (OpenAI, cost-effective), `BAAI/bge-small-en-v1.5` (free, local), Cohere Embed v3. Blocks Phase 2 (ingestion) until picked.
2. **LLM** — *reopened 2026-08-15.* GPT-4o-mini is mid-retirement and is no longer treated as even a provisional default. Candidates requiring a fresh head-to-head cost/quality evaluation: GPT-5-mini/nano, Claude Haiku 4.5, Gemini Flash. Also weigh using a different (stronger) model for RAGAS grading than for answer generation, to avoid judge/generator self-enhancement bias. Blocks Phase 4 (RAG core generation).
3. **Multi-document / cross-filing retrieval** (e.g., FY2023 vs FY2024, Company A vs B) — explicitly deferred, no target phase confirmed beyond "Phase 4 or later" in the original roadmap; unaffected by this revision.
4. **XBRL concept map completeness** *(new)* — the ~15-20 `us-gaap:*` concepts needed for the 6 dashboard ratios must be hand-verified against real Apple filing data before being trusted; not yet built or verified as of this reconciliation.

*(Structured-financials table naming is resolved — `structured_financials`, see Conflict 4/AD-012. Reconciliation validation is resolved as a requirement — see AD-014 — it is no longer listed as an open gap.)*

---

## 7. NON-NEGOTIABLE RULES (Hard Constraints)

1. Never compute financial ratios from RAG/LLM free text when structured extraction is available.
2. Never present an unsupported answer as factual — refuse explicitly when evidence is missing.
3. Never guess a missing value — show "Insufficient data" instead.
4. Never treat this as a generic chatbot project — it is a financial intelligence system.
5. Never replace an architecture component without a documented reason, migration effort, and risk assessment (see Section 5 for the model to follow).
6. Never sacrifice deployment/recruiter usability — the system must stay live and demo-able.
7. Never adopt expensive always-on infrastructure when a free/near-free alternative suffices.
8. Never hide uncertainty — distinguish facts, estimates, and speculation explicitly.
9. Never add multi-agent/agentic complexity before core ingestion quality, retrieval quality, and refusal behavior are proven (LangGraph StateGraph is sufficient for current scope).
10. Never flatten tables into unstructured prose during parsing or chunking.
11. *(new)* Never accept a `structured_financials` value with a failed reconciliation check silently — a `reconciled=FALSE` row must surface as a visible data-quality flag, never be treated as equivalent to a passing value.
12. *(new)* Never let a coding tool silently pick the LLM, embedding model, retry-cap value, faithfulness threshold, XBRL concept map, or golden-set answers — these are human/Architect-verified values, not implementation details a coding tool infers.

---

## 8. IMPLEMENTATION STATUS (as of last reconciliation)

**Completed:** Architecture fully decided (14 accepted decisions, 6 resolved conflicts documented above); tech stack finalized including the XBRL-hybrid structured-extraction path; UI/UX spec written; evaluation framework designed; repository structure planned (see `execution-plan.md` Part 6 for the exact folder tree); three-tool build workflow defined (Claude Architect / Claude Reviewer / OpenCode Implementer, see execution plan Part 1).

**Not started:** Repository does not exist. No parser, chunker, extractor, XBRL client/normalizer, retrieval, LangGraph, frontend, or evaluation code written. No Supabase project provisioned. No sample filings downloaded. Embedding model and LLM undecided (Section 6).

**Immediate next actions (in order, per the execution plan's phase roadmap):**
1. Lock the embedding model and LLM (Section 6) — both block downstream phases and must not be silently defaulted.
2. Scaffold the repo per the execution plan's folder structure (Phase 0): `backend/`, `frontend/`, `docs/`, including the two new tracking files `docs/DECISION_LOG.md` and `docs/DEV_LOG.md`.
3. Build `edgar_client.py` (Phase 1): CIK resolver, submissions fetcher, Company Facts fetcher, raw-filing fetcher — rate-limited and User-Agent compliant.
4. Build Path A ingestion end-to-end on one filing (Phase 2: Docling → chunker → metadata → embeddings → `chunks`).
5. Build Path B structured extraction (Phase 3): `xbrl/concept_map.py` (hand-verified against real Apple data) → `xbrl/normalizer.py` → `xbrl/reconciliation.py` → `structured_financials`, with `extractor_fallback.py` demoted and logged.
6. Build the Phase 4 minimal 3-node LangGraph path (Classifier → Retrieve/Generate → Refusal) and validate against a 10-question test set before starting Phase 5's full 8-node expansion.

**Downstream phases (5-8: full LangGraph, frontend, evaluation, deployment) follow the roadmap already detailed in `execution-plan.md` Part 2 and are unaffected by this revision beyond the sequencing already noted above.**
