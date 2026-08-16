# DEPLOYMENT.md — Ask My Filings

**Status:** Placeholder (Phase 0 scaffold). Full content lands in Phase 8 (execution plan Part 2).

## Locked decisions (TECH_DECISIONS.md, Decision 10)

- **Frontend:** Vercel — static React build.
- **Backend:** Railway — persistent FastAPI/Uvicorn process. (Vercel serverless's 10-second timeout breaks multi-call LangGraph pipelines and SSE streaming.)
- **Data:** Supabase — Postgres + pgvector + Storage.

## Phase 8 checklist (TBD)

- [ ] Railway service + environment variables
- [ ] Vercel project + build config
- [ ] Supabase production config
- [ ] Pre-seeded demo filing (e.g., Apple 10-K) so recruiters need not upload
- [ ] Cold, unauthenticated URL visit verified from a non-dev device

## Environment variables

See `.env.example`. Never commit real secrets.