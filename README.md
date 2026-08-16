# Ask My Filings

Portfolio-grade financial document intelligence system. Users upload SEC filings (10-K / 10-Q) and:

- Ask grounded questions and receive citation-backed answers
- Get automatic refusal when evidence is insufficient (never a guess)
- View financial ratios computed deterministically from structured data (XBRL-primary)
- Interact through a live, recruiter-usable, deployed system

**Status:** Phase 0 scaffold — repository structure and placeholder files only. No application code written. Architecture is locked; see `docs/`.

## Documentation (read first)

| File | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | System design, data flow, LangGraph topology, schema |
| `docs/TECH_DECISIONS.md` | Locked technology decisions |
| `docs/PROJECT_MEMORY.md` | Project state, decisions, hard constraints |
| `docs/execution-plan.md` | Build roadmap (Phases 0-8) |

## Repository structure

```
├── backend/          # FastAPI + ingestion + XBRL + LangGraph + RAG
│   ├── edgar/        #   SEC EDGAR client (Phase 1)
│   ├── ingestion/    #   Docling parser, chunker, metadata, embeddings (Phase 2)
│   ├── xbrl/         #   normalizer, concept_map, reconciliation (Phase 3)
│   ├── graph/nodes/  #   LangGraph 8-node topology (Phase 4-5)
│   ├── rag/          #   retrieval, generation, prompts (Phase 4)
│   ├── db/           #   Supabase schema + access
│   └── tests/
├── frontend/src/     # React + TypeScript + Tailwind + shadcn/ui + Vite (Phase 6)
├── eval/             # golden test set + RAGAS scoring (Phase 7)
└── docs/             # memory files, decision/dev/deployment logs, prompts
```

## Getting started

Placeholder — backend and frontend setup instructions land at Phase 0 completion (execution plan Part 2). See `.env.example` for required environment variables.

## Roadmap

Phase 0 preparation → Phase 1 EDGAR client → Phase 2 narrative ingestion → Phase 3 XBRL structured pipeline → Phase 4 minimal RAG graph → Phase 5 full 8-node LangGraph → Phase 6 frontend → Phase 7 evaluation → Phase 8 deployment.