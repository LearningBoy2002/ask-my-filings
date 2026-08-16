# ARCHITECTURE.md — Ask My Filings
**Status:** Final accepted architecture (pre-implementation — no code written yet)
**Last reconciled:** 2026-08-15
**Purpose:** Single authoritative technical architecture reference for Claude Projects. Supersedes all earlier system-design drafts, HTML design docs, and chunking-spec conversations. Where earlier material conflicts with this file, this file wins.

**Revision note (2026-08-15):** This revision incorporates two locked decisions from `ask-my-filings-viability-review.md` (XBRL-primary structured extraction; LLM decision reopened) and one sequencing change from `ask-my-filings-execution-plan.md` (minimal 3-node LangGraph built and validated before the full 8-node topology). No other architectural component changed. Feed this file, `TECH_DECISIONS.md`, and `PROJECT_MEMORY.md` to OpenCode/DeepSeek as the ground-truth spec for a from-scratch build.

---

## 1. SYSTEM DIAGRAM

```
┌──────────────────────────────────────────────────────────────┐
│                     USER (Browser)                            │
└───────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
┌───────────────────────────▼────────────────────────────────────┐
│  FRONTEND — React + TypeScript + Tailwind + shadcn/ui + Vite   │
│  Panel 1: Upload + ingestion progress                          │
│  Panel 2: Analytics Dashboard (KPI cards)                      │
│  Panel 3: RAG Chat (SSE token streaming)                       │
└───────────┬──────────────────────────────────┬─────────────────┘
       REST │ /api/ingest, /api/dashboard   SSE │ /api/chat
┌───────────▼──────────────────────────────────▼─────────────────┐
│  BACKEND — Python + FastAPI + Uvicorn                          │
│  ┌────────────────────────┐   ┌──────────────────────────────┐ │
│  │  INGESTION — TWO PATHS  │   │  LANGGRAPH STATEGRAPH          │ │
│  │  (A) Narrative/Table:   │   │  Phase 4: minimal 3-node        │ │
│  │      Docling → Chunker  │   │  Phase 5: full 8-node            │ │
│  │      → Metadata →       │   │  see Section 3                  │ │
│  │      Embedder           │   │                                │ │
│  │  (B) Structured facts:  │   │                                │ │
│  │      EDGAR XBRL Client  │   │                                │ │
│  │      → Normalizer →     │   │                                │ │
│  │      Reconciliation     │   │                                │ │
│  │      (Docling extractor │   │                                │ │
│  │       = fallback only)  │   │                                │ │
│  └───────────┬─────────────┘   └──────────────┬─────────────────┘ │
└──────────────┼────────────────────────────────┼───────────────────┘
               ▼                                ▼
┌──────────────────────────────────────────────────────────────┐
│  SUPABASE — Postgres + pgvector + Storage                      │
│  documents | chunks (+embeddings) | structured_financials      │
│  (BM25 index maintained alongside, application-side)           │
└──────────────────────────────────────────────────────────────┘

Observability: Langfuse traces every LangGraph node (latency, cost, failures)
Evaluation: RAGAS + GitHub Actions CI — blocks merge if faithfulness < 0.85
            (CI gate wired as blocking only from Phase 8 onward — see TECH_DECISIONS.md §9)
Deployment: Vercel (frontend, static) + Railway (backend, persistent) + Supabase (data)
```

**Local dev:** Vite dev server (`localhost:5173`, hot reload) + Uvicorn (`localhost:8000`); Supabase accessed remotely even in local dev.
**Production:** Vercel serves the compiled React build; Railway runs the persistent FastAPI/Uvicorn process (chosen specifically because Vercel serverless functions have a 10-second timeout that breaks multi-call LangGraph pipelines).

---

## 2. DATA FLOW

### 2.1 Ingestion flow — Path A: Narrative & table chunking (unchanged)
```
User uploads 10-K/10-Q PDF (or system fetches raw filing via EDGAR client)
  → POST /api/ingest
  → Docling parses into structured element tree
      (titles, headings, narrative text, tables, footnotes; headers/footers discarded)
  → Hierarchical chunker splits into:
      Level 1: Section (Item 1, Item 7, Note sections) — filter only, not a chunk
      Level 2: Element chunks (narrative blocks, tables, footnotes) — primary retrieval unit
      Level 3: Sub-table chunks for oversized tables (title/units/headers repeated in each)
  → Metadata tagger attaches: company, ticker, form_type, filing_date, fiscal_period,
      fiscal_year, item_number, section_title, subsection_title, page_number,
      chunk_type, table_title, source_file
  → Embedding model generates vectors for text chunks (model TBD — see Section 7)
  → All artifacts persisted to Supabase (documents, chunks+embeddings)
  → Frontend shows live progress: Parsing → Chunking → Embedding → Storage
```

### 2.2 Ingestion flow — Path B: Structured financial extraction (XBRL-primary)
```
Target filing identified (CIK + accession number)
  → EDGAR XBRL Client fetches SEC Company Facts API (data.sec.gov) —
      machine-readable, issuer-attested, GAAP-tagged JSON, no PDF parsing required
  → Normalizer walks the Company Facts JSON, applies a static concept map
      (~15-20 required us-gaap:* concepts → the 6 dashboard ratios' inputs),
      resolves the correct fiscal period, applies correct scale/units
  → Reconciliation module cross-checks internal consistency
      (e.g. AssetsCurrent + AssetsNoncurrent = Assets;
           Liabilities + StockholdersEquity = Assets)
      and flags reconciled=FALSE on mismatch rather than silently proceeding
  → Rows written to `structured_financials` with source='xbrl_companyfacts'
  → FALLBACK PATH (Docling-based extractor.py — demoted, not primary):
      invoked ONLY when a required concept has no XBRL tag for this filer
      → writes rows with source='docling_fallback'
      → every fallback invocation is logged (concept + company) so fallback
        frequency is visible and auditable, not silent
  → structured_financials remains SEPARATE from text chunks — this pipeline
      never merges back into the chunk table (AD-007, unchanged)
```

**Why this order matters:** Path B no longer depends on Path A. Docling/chunking failures on a complex table can degrade retrieval (Workload A) but can no longer silently corrupt a financial ratio (Workload B) — the system's single highest-stakes failure mode is now covered by issuer-attested data first, PDF-table extraction second.

### 2.3 Query flow
```
User submits a question in chat
  → POST /api/chat (SSE)
  → LangGraph StateGraph executes (see Section 3 — minimal graph in Phase 4,
      full 8-node graph from Phase 5 onward)
  → Response streamed token-by-token to frontend with inline citations
     (document name, section, page)
  → If evidence insufficient at any validation point → explicit refusal, no guess
```

### 2.4 Dashboard flow (fully decoupled from chat)
```
Frontend loads dashboard
  → GET /api/dashboard
  → Backend reads ONLY from `structured_financials` table
  → Ratios computed with plain backend arithmetic (Section 5 formulas)
  → Any missing required field → "Insufficient data" for that metric, never a guess
  → Any reconciled=FALSE record surfaces as a visible data-quality flag, not a
     silently-accepted number
  → Zero coupling to the RAG/chat pipeline — this is the core architectural
     guarantee that separates deterministic analytics from probabilistic retrieval
```

---

## 3. LANGGRAPH FLOW

**Build sequencing (new — from execution plan):** The 8-node topology below is the
locked target architecture and does not change. What changes is *build order*:
a minimal 3-node graph (Query Classifier → combined Retrieve/Generate →
Refusal Node) is built, wired, and validated against a 10-question test set
FIRST (Phase 4). HyDE, the Reranker, the Hallucination Guard, and Retry Logic
are layered in AFTERWARD as Phase 5, around the already-working core. This is
a sequencing discipline, not a scope reduction — do not treat the minimal
graph as the final deliverable.

**Target: 8-node StateGraph** (`AgentState` as TypedDict; conditional edges for routing and retry):

```
[Query Classifier]
   ├─ structured metric query ──────────────────► [Structured Lookup] ──► response
   ├─ ambiguous / no evidence expected ─────────► [Refusal Node] ────────► response
   └─ document Q&A ──► [Query Rewriter / HyDE (conditional, Phase 5)]
                              │
                              ▼
                     [Retrieval Node: BM25 ∥ pgvector, merged via RRF]
                              │
                              ▼
                     [Reranker Node (Phase 5): cross-encoder on top-K]
                              │
                              ▼
                     [Generation Node: citation-enforced]
                              │
                              ▼
                     [Hallucination Guard (Phase 5)]
                        ├─ pass ──────────────────────────► stream response
                        └─ fail ──► [Retry Logic (Phase 5)]
                                       ├─ attempts < 2 ──► back to Retrieval Node
                                       └─ attempts = 2 ──► [Refusal Node] ──► response
```

**Phase 4 minimal graph (build and validate this first):**
```
[Query Classifier] ──► [Retrieve + Generate (single combined node)] ──► response
                   └──► [Refusal Node] ──► response
```
Uses the same hybrid BM25+pgvector retrieval and citation-enforced generation
logic as the target graph — just without HyDE, reranking, hallucination
guarding, or retry. Validated against 10 hand-picked questions (factual,
table-based, unanswerable) before Phase 5 begins.

**Node responsibilities (target 8-node graph):**
| Node | Function | Phase introduced |
|---|---|---|
| Query Classifier | Routes to structured lookup / RAG chain / refusal; short-circuits vague queries to save ~30% token cost | Phase 4 |
| Query Rewriter / HyDE | Triggered ONLY when classifier flags query as short/ambiguous; generates a hypothetical answer, embeds that instead of the raw query to close the query-vs-document vector-space gap | Phase 5 |
| Retrieval Node | Runs BM25 (exact-term) and pgvector (semantic) in parallel; merges via Reciprocal Rank Fusion | Phase 4 |
| Reranker Node | Cross-encoder scores (query, chunk) pairs jointly on the retrieved top-K only (not full corpus) — controls the ~100–200ms latency cost | Phase 5 |
| Generation Node | Produces the answer; every factual claim must map to a retrieved chunk | Phase 4 |
| Hallucination Guard | Validates citation coverage and evidence support before the answer reaches the user | Phase 5 |
| Refusal Node | Explicit "insufficient evidence" response — never a plausible-sounding guess | Phase 4 |
| Retry Logic | Hard cap of 2 retries before permanent fallback to Refusal Node — prevents runaway loops | Phase 5 |

**HyDE — two distinct applications (not one), both Phase 5+:**
1. Query-time: hypothetical answer generated and embedded in place of the raw query (conditional trigger only).
2. Ingestion-time: hypothetical questions pre-generated per chunk and stored as chunk metadata, enabling question-to-question matching at retrieval.

---

## 4. RAG PIPELINE

| Stage | Design |
|---|---|
| **Parsing** | Docling — structure-aware; preserves headings, reading order, tables, hierarchy. Chosen over PyMuPDF/pdfplumber, which flatten tables into unreadable text. Feeds Path A (narrative/table chunking) only — no longer the primary source of `structured_financials`. |
| **Chunking** | Hierarchical, element-based, table-aware (3-level, see Section 2.1). Narrative chunk target: 350–600 tokens, hard cap ~700. Tables kept atomic where possible; oversized tables split by logical row/year groups with headers repeated in every subchunk. Fixed-token, sliding-window, and sentence-based chunking are explicitly demoted to fallback-only status — they ignore filing structure and split tables from captions. |
| **Embeddings** | **Model not yet finalized** (open architectural gap — see Section 7). Candidates: `text-embedding-3-small`, `bge-small-en-v1.5`, Cohere Embed v3. |
| **Retrieval** | Hybrid: BM25 (exact financial terms — tickers, "EBITDA," "Item 7") run in parallel with pgvector dense search (semantic intent); merged via Reciprocal Rank Fusion (rank-based, no score calibration needed). Vector-only and BM25-only are both explicitly rejected as insufficient alone. |
| **Reranking** | Cross-encoder (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) rescoring the retrieved top-K jointly against the query — applied after hybrid retrieval, not on the full corpus. Layered in at Phase 5, not Phase 4. |
| **Generation** | Citation-enforced: every claim in the answer must be grounded in a specific retrieved chunk; prompts version-controlled in `config.yaml`, never hardcoded. |
| **Validation** | Hallucination Guard checks citation coverage and evidence support before the response streams to the user; failure routes to Retry Logic (max 2 attempts) then Refusal Node. Layered in at Phase 5. |
| **Structured extraction** | XBRL Company Facts API (primary) + Docling-based extractor (fallback only) — see Section 2.2. This is the single biggest change from the original design and directly protects Hard Constraint #1. |

---

## 5. DATABASE SCHEMA

Supabase (Postgres + pgvector). No DDL has been executed yet — this is the finalized design to implement.

**`documents`**
| Column | Notes |
|---|---|
| doc_id (PK) | |
| source_file | original filename |
| company, ticker | |
| form_type | 10-K / 10-Q |
| filing_date, fiscal_year | |
| cik | SEC Central Index Key — required for XBRL Company Facts lookups |
| accession_number | SEC filing accession number, for EDGAR traceability |

**`chunks`**
| Column | Notes |
|---|---|
| chunk_id (PK) | |
| document_id (FK → documents.doc_id) | |
| embedding | pgvector column |
| text | chunk content used for retrieval |
| company, ticker, form_type, filing_date, fiscal_period, fiscal_year | denormalized for fast metadata filtering |
| item_number, section_title, subsection_title | |
| page_number | |
| chunk_type | narrative / table / footnote |
| table_title | nullable, table chunks only |
| source_file | |

**`structured_financials`** *(standardized name — previously referred to inconsistently as `structured_tables` / `table_rows` across earlier sessions; this is now the single canonical name)*
| Column | Notes |
|---|---|
| record_id (PK) | |
| document_id (FK → documents.doc_id) | |
| line_item | e.g. "Net income", "Total shareholders' equity" |
| value | numeric |
| period | fiscal period this value applies to |
| units | e.g. "millions", "thousands" |
| currency | |
| concept_tag | *(new)* the `us-gaap:*` XBRL concept name when `source='xbrl_companyfacts'`; null for fallback rows |
| source | *(new)* `'xbrl_companyfacts'` \| `'docling_fallback'` — required, never null; makes provenance auditable per record |
| reconciled | *(new)* boolean, nullable — set by the reconciliation module; `FALSE` must surface as a visible data-quality flag on the dashboard, never be silently dropped |

**`citations`** *(optional, lower-priority — mentioned once, not required for MVP)*
| Column | Notes |
|---|---|
| citation_id (PK) | |
| chunk_id (FK → chunks.chunk_id) | |
| answer_span | maps generated answer text back to source |

**Relationships:** `chunks.document_id` → `documents.doc_id`; `structured_financials.document_id` → `documents.doc_id`. **By design, `chunks` and `structured_financials` are never joined at query time for ratio computation** — this enforces AD-007 (dashboard reads only structured data, RAG chat reads only chunks). This constraint is unaffected by the XBRL-primary change — XBRL and Docling-fallback rows both land in the same `structured_financials` table, distinguished only by the new `source` column.

**Metadata strategy:** Metadata on `chunks` is a first-class filtering mechanism, not decoration — enables SQL WHERE filtering (ticker + fiscal_year + chunk_type) combined with vector similarity in a single query, and lets retrieval distinguish a risk-factor narrative from a footnote or a prior-year figure from a current-year one.

---

## 6. CONFLICT RESOLUTION LOG
*(Architecture-relevant conflicts only; full decision history lives in PROJECT_MEMORY.md)*

### Conflict 1 — Vector/relational storage
**Previous Decision:** Neon serverless Postgres + pgvector for production.
**Updated Decision:** Supabase (Postgres + pgvector + Storage).
**Reason for Change:** Neon is database-only; Supabase bundles vector search, SQL metadata filtering, file storage for uploaded PDFs, and an auth/RLS path in a single free-tier service — fewer moving parts for a live recruiter demo.

### Conflict 2 — Document parser
**Previous Decision:** PyMuPDF (implied default in earliest brief).
**Updated Decision:** Docling.
**Reason for Change:** Cited comparison showed ~94% table-structure accuracy for Docling vs. ~45% for PyMuPDF on a 10-K-style document. Table fidelity is load-bearing for retrieval; see Conflict 5 for why it is no longer load-bearing for structured-financials extraction specifically.

### Conflict 3 — Chunking strategy
**Previous Decision:** Not explicitly stated in the earliest brief (generic "structure-aware chunking" only).
**Updated Decision:** Hierarchical, element-based, table-aware chunking with a strict 3-level structure (Section 2.1), and fixed-token/sliding-window/sentence-based chunking demoted to fallback-only.
**Reason for Change:** Research cited on financial-report RAG found element-based chunking outperforms fixed-token chunking on financial Q&A accuracy without requiring heavy chunk-size tuning; fixed/sliding-window approaches regularly split tables from captions.

### Conflict 4 — Structured financials table naming
**Previous Decision:** Referred to inconsistently across sessions as `structured_tables`, `structured_financials`, and `table_rows`.
**Updated Decision:** `structured_financials` (Section 5).
**Reason for Change:** No functional disagreement existed, only naming drift across conversations. A single canonical name is required before any DDL or ORM model is written, to avoid the exact multi-conversation inconsistency Claude Code best practices warn against.

### Conflict 5 — Structured financials data source *(new, 2026-08-15)*
**Previous Decision:** `structured_financials` populated exclusively via a custom Docling-based PDF table extractor (`extractor.py`).
**Updated Decision:** SEC's free XBRL Company Facts API (`data.sec.gov`) is the primary source, feeding `normalizer.py` + `reconciliation.py`. The Docling-based extractor is retained but demoted to a fallback, invoked only when a required `us-gaap:*` concept is missing for a given filer.
**Reason for Change:** The SEC already publishes every GAAP-tagged line item as free, machine-readable, issuer-attested JSON — no PDF parsing required. Building a bespoke table-extraction path to reconstruct data the filer already structured and certified was the largest unforced correctness risk in a system whose #1 hard constraint is "never guess a financial number." This also preemptively answers the near-certain interviewer question "why not just use the XBRL API?" Migration cost is low: additive, no schema change beyond three new columns on `structured_financials` (Section 5), and Docling/chunking (Path A) is completely untouched.

### Conflict 6 — LLM lock status *(new, 2026-08-15)*
**Previous Decision:** GPT-4o-mini treated as the effectively-locked budget default in some project-instruction contexts, while simultaneously listed as an open decision in all three memory files.
**Updated Decision:** Formally reopened, not locked. Must be re-evaluated before Phase 2/4 generation work begins — see TECH_DECISIONS.md Open Decisions and Section 7 below.
**Reason for Change:** GPT-4o-mini is actively being retired across OpenAI's product surfaces during 2026 (ChatGPT access to GPT-4o retired February 13, 2026; Azure Foundry lists a GPT-4o-mini retirement date of March 31, 2026). Locking prompts and evals to a model mid-retirement creates avoidable rework. Candidates for re-evaluation: GPT-5-mini/nano, Claude Haiku 4.5, Gemini Flash.

---

## 7. OPEN ARCHITECTURAL GAPS (not yet resolved — do not assume a default)

1. **Embedding model** — blocks chunk embedding step in Section 2.1 and the `chunks.embedding` column definition. Candidates: `text-embedding-3-small`, `bge-small-en-v1.5`, Cohere Embed v3.
2. **LLM** — reopened (Conflict 6). GPT-4o-mini is mid-retirement and must not be silently defaulted to. Affects Generation Node cost/latency in Section 3. Candidates: GPT-5-mini/nano, Claude Haiku 4.5, Gemini Flash — needs a head-to-head cost/quality pass before Phase 2 (RAG core) generation work begins.
3. **`citations` table** — optional; not required for MVP, revisit after Phase 2.
4. **Multi-document / cross-filing retrieval** (FY2023 vs FY2024, Company A vs B) — explicitly deferred beyond current phase roadmap.

*(Reconciliation validation for `structured_financials` is no longer an open gap — it is now a designed-in requirement inside the XBRL pipeline, Section 2.2, protecting Hard Constraint #1 directly.)*
