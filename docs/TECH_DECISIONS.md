# TECH_DECISIONS.md — Ask My Filings
**Status:** Final accepted decisions (pre-implementation — no code written yet)
**Last reconciled:** 2026-08-15
**Purpose:** Single authoritative decision log for Claude Projects. Every technology choice below is locked. Do not propose alternatives to a locked decision unless a concrete new technical blocker is found — if you do, it must be logged here in the Conflict Resolution format, not silently substituted.

**Revision note (2026-08-15):** Adds Decision 12 (XBRL-primary structured extraction) and reopens the LLM decision (Conflict 6 below), per `ask-my-filings-viability-review.md`. Adds a build-sequencing note to Decision 6 (LangGraph) per `ask-my-filings-execution-plan.md`. No other locked decision changed.

---

## 1. PARSER — Docling

**Decision:** Use Docling for all document ingestion and parsing.

**Why:** Financial filings are table-heavy with merged cells, multi-level headers, and irregular layouts. Docling is structure-aware — it preserves headings, reading order, tables, and document hierarchy, and exports to structured Markdown/JSON. A cited head-to-head comparison found ~94% table-structure accuracy for Docling vs. ~45% for PyMuPDF on a 10-K-style document.

**Scope note (2026-08-15):** Docling remains the parser for narrative/table chunking feeding the RAG chat workload (`chunks` table). It is **no longer the primary source** for `structured_financials` — see Decision 12. Docling-based extraction is retained only as a fallback for XBRL-uncovered concepts.

**Alternatives Rejected:**
- **PyMuPDF** — flattens tables into unreadable text blobs; structure-blind.
- **pdfplumber** — weak on complex, multi-level table headers.
- **LlamaParse** — paid, adds an external dependency; rejected on cost grounds for a budget-conscious build.

**Tradeoffs:** Docling is not magic — complex tables (merged cells, multi-page tables) can still be misread. This remains a real risk for Path A (chat retrieval quality) but is no longer a risk for dashboard ratio correctness, since Decision 12 removes Docling from that critical path.

---

## 2. FRONTEND — React + TypeScript + Tailwind + shadcn/ui + Vite

**Decision:** Use React + TypeScript + Tailwind CSS + shadcn/ui + Vite for the entire frontend.

**Why:** The UI requires three simultaneously-active states — file upload with live ingestion progress, a token-streaming chat, and a static analytics dashboard. shadcn/ui provides production-ready dashboard/chat component templates out of the box (Card, Table, Badge, chat primitives), and Vite gives instant hot-reload during development.

**Alternatives Rejected:**
- **Streamlit** — re-runs the entire script on every interaction; cannot cleanly isolate a static dashboard panel from a live-streaming chat panel without hacks (ratio cards would recompute on every chat message). Also produces a "data-science demo" aesthetic, not a product.
- **Next.js** — deemed unnecessarily complex for this project's scale; Vite is sufficient.

**Tradeoffs:** Slower to build than Streamlit — a real weekend-vs-6-weeks tradeoff was explicitly discussed. Accepted because the target roles (analytics, fintech, consulting) reward full-stack signal over speed-to-demo.

---

## 3. BACKEND — Python + FastAPI + Uvicorn

**Decision:** Use Python + FastAPI as the sole backend orchestration and serving layer.

**Why:** All major AI SDKs, evaluation libraries (RAGAS), parsing tools (Docling), and orchestration frameworks (LangChain/LangGraph) are Python-first. FastAPI supports Server-Sent Events for token-by-token streaming, which the chat UX requires.

**Alternatives Rejected:**
- **Node.js backend** — would require bridging to Python AI libraries; adds a language boundary with no benefit.
- **Django** — too heavyweight and opinionated for an API-first RAG backend.

**Tradeoffs:** None significant — this was one of the least contested decisions in the project.

---

## 4. STORAGE — Supabase (Postgres + pgvector + Storage)

**Decision:** Use Supabase as the production storage layer for vectors, structured financial data, and uploaded files.

**Why:** Supabase bundles pgvector, SQL metadata filtering alongside vector similarity in one query, file storage for uploaded PDFs, and a row-level-security auth path — all in one free-tier service. ChromaDB is retained for local prototyping only.

**Alternatives Rejected:**
- **ChromaDB (production)** — ephemeral on cloud restarts (Railway/Hugging Face free tiers); data evaporates on every container restart. Unacceptable for a live recruiter demo. Still used for local prototyping.
- **Pinecone** — paid managed service; cost risk at scale, vendor lock-in.
- **Weaviate** — self-hosting complexity is overkill for this project's scale.
- **Neon (serverless Postgres + pgvector)** — was the project's original storage choice. Database-only; lacks bundled file storage and an equally simple auth path.

**Tradeoffs:** Supabase free tier has real limits — inactivity pauses, storage caps, connection pool constraints — acceptable at demo scale but must be disclosed honestly, not implied away, if the project scales.

---

## 5. RETRIEVAL — BM25 + pgvector hybrid, merged via Reciprocal Rank Fusion, then cross-encoder reranking

**Decision:** Retrieval always runs BM25 and dense vector search in parallel, merges via RRF, then reranks the top-K with a cross-encoder.

**Why:** Dense vector-only retrieval fails on exact financial-term queries (tickers, "EBITDA," specific line items, "Item 7"). BM25 handles exact-term matching precisely. Combined, they cover both semantic intent and lexical precision. Cross-encoder reranking jointly scores each (query, chunk) pair, materially improving precision, especially on table-based questions.

**Build sequencing note (2026-08-15):** Hybrid BM25+pgvector retrieval with RRF ships in the Phase 4 minimal graph. Cross-encoder reranking is layered in at Phase 5 — see Decision 6.

**Alternatives Rejected:**
- **Vector-only retrieval** — misses exact financial terms.
- **BM25-only retrieval** — misses semantic intent entirely.
- **No reranking** — leaves lower context precision, particularly damaging on table questions.

**Tradeoffs:** Cross-encoder reranking adds ~100–200ms latency and must only run on the top-K from hybrid retrieval, never the full corpus, or cost/latency become unacceptable.

---

## 6. WORKFLOW ORCHESTRATION — LangGraph 8-node StateGraph

**Decision:** Use LangGraph as the workflow control layer, implementing an 8-node StateGraph (Query Classifier, Query Rewriter/HyDE, Retrieval, Reranker, Generation, Hallucination Guard, Refusal, Retry Logic).

**Why:** The system needs routing between distinct query types, conditional retry logic with hard limits, validation gates before output reaches the user, and stateful context passing — patterns that bare LangChain chains (which are linear) cannot express.

**Build sequencing (2026-08-15, new):** The 8-node topology is the locked target and does not change. Build order does: a minimal 3-node graph (Query Classifier → combined Retrieve/Generate → Refusal) is built and validated against a 10-question test set in Phase 4, before HyDE, Reranker, Hallucination Guard, and Retry Logic are layered in as Phase 5. This directly addresses the project's own self-flagged risk that LangGraph's async conditional-edge logic is "a known source of subtle bugs" and that node-isolation testing was "not yet practiced." Each of the 4 Phase-5 nodes must be unit-tested in isolation before being wired into the graph.

**Alternatives Rejected:**
- **Bare LangChain only** — linear chains, no conditional routing.
- **Custom state machine** — would require building all the plumbing (typed state, conditional edges, tracing integration) from scratch that LangGraph already provides.
- **Full multi-agent framework** — explicitly rejected as premature; adds orchestration complexity before core ingestion/retrieval/refusal quality is proven. May be revisited only if the core pipeline is stable.
- **Building all 8 nodes before anything runs end-to-end** — rejected as a build strategy (not a topology alternative) per the sequencing note above; the risk of debugging 8 untested nodes at once outweighs any time saved.

**Tradeoffs:** LangGraph's async conditional-edge logic is a known source of subtle bugs. Mitigation: minimal-graph-first sequencing (above) plus isolated node testing before graph assembly.

---

## 7. FINANCIAL RATIO COMPUTATION — Deterministic structured extraction, never RAG free-text

**Decision:** All dashboard ratios (Gross Margin, Net Profit Margin, ROE, Debt-to-Equity, Current Ratio, P/E) are computed from typed numeric fields extracted and stored separately during ingestion. RAG/LLM output is never used to derive these numbers.

**Why:** This is the single most important constraint in the whole project. Computing ratios from LLM free text creates a category of confident-but-wrong numbers — the model can misread units ("thousands" vs "millions"), confuse prior-year vs current-year figures, or hallucinate a plausible number with no grounding. Any finance-literate interviewer would identify this immediately as a design flaw.

**Reinforced by Decision 12 (2026-08-15):** Sourcing these typed fields from XBRL (issuer-attested) rather than PDF-table extraction closes the largest remaining gap in this constraint — a mis-parsed Docling table could previously have silently fed a wrong number into a "deterministic" pipeline. XBRL removes that failure mode for any concept it covers.

**Alternatives Rejected:**
- **Computing ratios from RAG output** — hard-rejected as a non-negotiable constraint, not merely deprioritized.

**Tradeoffs:** Requires a dedicated structured-extraction module. If extraction fails for a field (from both XBRL and the Docling fallback), the dashboard must show "Insufficient data" rather than guessing — this is treated as correct behavior, not a defect.

---

## 8. CHUNKING STRATEGY — Hierarchical, element-based, table-aware

**Decision:** Use a 3-level hierarchy (Section → Element chunk → Sub-table chunk) with mandatory table-aware treatment; tables are never flattened into prose.

**Why:** Cited research on financial-report RAG found element-based chunking outperforms fixed-token chunking on financial Q&A accuracy without heavy chunk-size tuning. SEC filings have strong structural signals (Item headings, table titles, note headers) that must be preserved as chunk boundaries and metadata.

**Alternatives Rejected:**
- **Fixed-size token chunking** — structure-blind; regularly splits tables from captions; demoted to fallback-only status.
- **Sliding-window chunking** — creates duplicate vectors, structure-blind, expensive.
- **Sentence-based chunking** — too granular; loses financial context that spans multiple sentences.
- **Semantic chunking as primary** — unnecessary given how strong the explicit structural signals already are in SEC filings; usable only as a refinement, not a replacement.

**Tradeoffs:** Requires custom logic to detect Item headings, table boundaries, and repeat table titles/units/headers in every subchunk when splitting large tables — more implementation effort than a naive splitter.

---

## 9. EVALUATION & OBSERVABILITY — RAGAS + Langfuse + GitHub Actions CI

**Decision:** RAGAS for evaluation metrics, Langfuse for tracing, GitHub Actions for a CI regression gate on every PR (faithfulness ≥ 0.85 blocks merge).

**Why:** A portfolio project with no evaluation infrastructure is indistinguishable from a tutorial clone to a technical reviewer. RAGAS gives standardized, interpretable metrics; Langfuse gives node-level tracing for debugging retrieval failures; the CI gate ensures prompt or retrieval changes don't silently degrade quality.

**Sequencing note (2026-08-15):** The RAGAS scoring script is built in Phase 7, but the CI gate is wired as **non-blocking** until closer to Phase 8. Running it as a hard PR-blocking gate during active development (Phases 4-6) would mostly generate noisy failures on unfinished work, not real signal.

**Judge/generator note:** if a similarly-priced budget model both answers questions and grades faithfulness in RAGAS, LLM-judge self-enhancement and verbosity biases can inflate the safety numbers the gate depends on. Use a different (ideally stronger) model for grading than for generation — factor this into the LLM re-evaluation (Open Decisions, below).

**Alternatives Rejected:**
- **Manual testing only** — not regression-safe; cannot catch silent degradation across prompt/retrieval changes.
- **LangSmith** — originally considered, replaced by Langfuse for cost-effectiveness and open-source availability.

**Tradeoffs:** Requires maintaining a golden test set (factual, table-based, narrative, ambiguous/unanswerable, adversarial questions) — real ongoing maintenance overhead, not a one-time setup cost. Also requires manually spot-checking a sample of golden answers rather than trusting the RAGAS score blind (independent research found only moderate correlation between RAGAS faithfulness and human judgment).

---

## 10. DEPLOYMENT — Vercel (frontend) + Railway (backend) + Supabase (data)

**Decision:** Deploy the React frontend on Vercel, the FastAPI backend on Railway, with Supabase handling database and file storage.

**Why:** Vercel's serverless functions have a 10-second execution timeout — insufficient for LangGraph pipelines involving multiple LLM calls, reranking, and validation nodes. Railway provides persistent, long-running FastAPI hosting that supports SSE streaming without timeout constraints, at low cost.

**Alternatives Rejected:**
- **Vercel serverless for the backend** — 10s timeout breaks multi-call LangGraph pipelines.
- **Hugging Face Spaces** — ephemeral storage causes the same data-loss problem as ChromaDB on restart.
- **Self-hosted VPS** — operational overhead not justified at demo scale (~50 recruiter queries/month, ~$0.15/month target cost — subject to revision once the LLM decision is relocked, see Open Decisions).

**Tradeoffs:** Adds a second hosting platform (Railway) to manage alongside Vercel, versus a single-platform deploy — accepted because the alternative (serverless backend) is functionally broken for this workload.

---

## 11. HYDE (HYPOTHETICAL DOCUMENT EMBEDDINGS) — Conditional, dual-use

**Decision:** Use HyDE in two places: (1) query-time, generating a hypothetical answer to embed instead of the raw query, triggered only for short/ambiguous queries; (2) ingestion-time, pre-generating hypothetical questions per chunk for question-to-question matching.

**Why:** User queries and document chunks live in different semantic spaces — a question like "What risks does the company face?" is lexically dissimilar from an answer chunk starting "The company is exposed to regulatory changes..." HyDE bridges this gap by making the query "look like" a document before retrieval.

**Sequencing note (2026-08-15):** Both HyDE applications are Phase 5 additions, layered onto the already-working Phase 4 minimal graph — see Decision 6.

**Alternatives Rejected:**
- **Applying HyDE to every query unconditionally** — rejected; adds unnecessary latency and LLM cost on precise, well-formed financial queries that don't need it.

**Tradeoffs:** Adds one extra LLM call and measurable latency per triggered query. Explicitly accepted as a portfolio talking point demonstrating understanding of the retrieval-quality-vs-latency tradeoff — not applied indiscriminately.

---

## 12. STRUCTURED FINANCIAL EXTRACTION — XBRL Company Facts API (primary), Docling extractor (fallback) *(new, 2026-08-15)*

**Decision:** `structured_financials` is populated primarily from SEC's free XBRL Company Facts API (`data.sec.gov`) via `edgar_client.py` → `xbrl/normalizer.py` → `xbrl/reconciliation.py`. The previously-planned Docling-based `extractor.py` is retained but demoted to a fallback, invoked only when a required `us-gaap:*` concept is missing from a filer's XBRL data.

**Why:** XBRL data is machine-readable, time-stamped, issuer-attested, and directly comparable across companies — no PDF table parsing required for GAAP-tagged line items. Building a bespoke extraction path to reconstruct data the filer has already structured and certified was the single largest unforced correctness risk in a system whose #1 hard constraint is "never guess a financial number." It also preemptively answers the near-certain "why not just use the XBRL API?" question from a finance-literate reviewer.

**What this replaces:** `extractor.py`'s role as the *primary* path for `structured_financials`. It does not disappear — it becomes the fallback, and every fallback invocation is logged (concept + company) so its actual usage frequency is visible, not assumed.

**What this does NOT change:** Docling, the 3-level chunker, and the metadata tagger are untouched and continue to feed `chunks` for the RAG chat workload (Path A, unaffected). AD-007 (dashboard reads only `structured_financials`, chat reads only `chunks`, never joined) is untouched. LangGraph topology, retrieval, reranking, evaluation, and deployment are all untouched.

**Alternatives Rejected:**
- **Docling-only extraction as originally planned** — rejected as primary path; kept as fallback only, per above.
- **XBRL-only, no fallback** — rejected; not every required concept is guaranteed tagged for every filer, and a hard failure with no fallback would reduce dashboard coverage unnecessarily. The fallback must be visibly logged, never silent.

**Tradeoffs:** Adds a new ingestion branch (`edgar/client.py`, `xbrl/normalizer.py`, `xbrl/concept_map.py`, `xbrl/reconciliation.py`) alongside the existing Docling path. Migration cost is low — additive, no schema change beyond three new columns on `structured_financials` (`source`, `concept_tag`, `reconciled` — see ARCHITECTURE.md §5). Concept mapping (`concept_map.py`) must be hand-verified against real filing data before being trusted, not auto-generated by a coding tool.

---

## CONFLICT RESOLUTION LOG

### Conflict 1 — Storage
**Previous Decision:** Neon (serverless Postgres + pgvector).
**Updated Decision:** Supabase (Postgres + pgvector + Storage).
**Reason for Change:** Neon is database-only; Supabase bundles file storage and an auth path in the same free-tier service, reducing the number of platforms needed for the demo.

### Conflict 2 — Frontend
**Previous Decision:** Streamlit or Hugging Face Spaces (earliest project brief).
**Updated Decision:** React + TypeScript + Tailwind + shadcn/ui + Vite.
**Reason for Change:** Streamlit cannot cleanly support three simultaneous UI states (upload progress, streaming chat, static dashboard) without state-management hacks; React signals stronger full-stack capability to target recruiters.

### Conflict 3 — Parser
**Previous Decision:** PyMuPDF (implied default, not yet challenged in the earliest brief).
**Updated Decision:** Docling.
**Reason for Change:** ~94% vs ~45% table-structure accuracy in a cited head-to-head comparison; table fidelity is load-bearing for this project's retrieval layer (see Conflict 5 for its removal from the structured-extraction critical path).

### Conflict 4 — Deployment target
**Previous Decision:** Streamlit / Hugging Face Spaces.
**Updated Decision:** Vercel + Railway + Supabase.
**Reason for Change:** Follows directly from the frontend conflict (React, not Streamlit) and from the Vercel-serverless-timeout constraint on LangGraph; HF Spaces also shares ChromaDB's ephemeral-storage problem.

### Conflict 5 — Structured financials data source *(new, 2026-08-15)*
**Previous Decision:** Docling-based PDF table extraction as the sole source of `structured_financials`.
**Updated Decision:** XBRL Company Facts API as primary, Docling extraction demoted to fallback. See Decision 12.
**Reason for Change:** Removes the largest correctness risk from the most safety-critical part of the system; issuer-attested data beats reconstructing what the filer already structured. Additive change, low migration cost.

### Conflict 6 — LLM lock status *(new, 2026-08-15)*
**Previous Decision:** GPT-4o-mini treated as effectively locked in some project-instruction contexts.
**Updated Decision:** Formally reopened — see Open Decisions below.
**Reason for Change:** GPT-4o-mini is mid-retirement across OpenAI's product surfaces in 2026 (ChatGPT access to GPT-4o retired Feb 13, 2026; Azure Foundry retirement date of Mar 31, 2026 for gpt-4o-mini). Locking prompts/evals to a model mid-retirement creates avoidable rework — cheaper to decide now, before Phase 2/4 generation code exists, than after.

---

## OPEN DECISIONS — NOT YET LOCKED (do not suggest a default silently)

1. **Embedding model** — candidates: `text-embedding-3-small` (OpenAI), `bge-small-en-v1.5` (free, local), Cohere Embed v3. Blocks Phase 2 (ingestion embedding step).
2. **LLM** — *reopened 2026-08-15.* GPT-4o-mini is mid-retirement and must not be silently defaulted to. Candidates requiring a head-to-head cost/quality evaluation: GPT-5-mini/nano, Claude Haiku 4.5, Gemini Flash. Also consider using a different (stronger) model for RAGAS grading than for generation, to avoid judge/generator self-enhancement bias (Decision 9). Blocks Phase 4 (RAG core generation).

If asked to help decide either of these, treat it as an open decision requiring a recommendation with tradeoffs — not as something to silently pick and move on from.
