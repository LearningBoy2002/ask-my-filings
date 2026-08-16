# Ask My Filings — Project Viability & Architecture Review
**Reviewer role:** Senior AI Architect / Technical Advisor
**Basis:** ARCHITECTURE.md, TECH_DECISIONS.md, PROJECT_MEMORY.md (all dated 2026-08-10/11), plus current external research (cited inline)
**Scope note:** The review brief asked for comparison against legal-AI / contract-review platforms. That's a template mismatch — this project analyzes SEC filings, not contracts — so Section 4 compares against the actually relevant competitive set (financial-document intelligence platforms) and only touches legal AI where the underlying RAG-safety pattern genuinely overlaps.
 
---
 
## 1. Project Idea Assessment
 
**Problem being solved:** Reading and cross-referencing 100–300 page 10-K/10-Q filings is slow, and deriving financial ratios by hand from filing tables is error-prone (wrong period, wrong units, missight decimals). The project targets this with (a) citation-grounded Q&A over filing text and (b) ratios computed only from typed, extracted fields — never from LLM free text.
 
**Is the problem significant?** Yes, in the abstract — this is a real, well-documented pain point for equity analysts, and a real market has formed around it. But the market is already dense and well-funded: platforms like AlphaSense, Hebbia, Fintool, Daloopa, Calcbench, and Workiva's SEC Filing Intelligence all solve exactly this, several with direct EDGAR ingestion and enterprise data partnerships<cite index="7-1">that connect directly to EDGAR or its API and ingest filings at or near publication</cite>. So the problem is real, but it is not underserved.
 
**Who are the likely users?** Two very different answers depending on framing:
- *As stated in the project brief:* equity analysts, retail investors doing diligence.
- *As the project actually functions:* a recruiter or interviewer spending a few minutes evaluating a candidate's engineering judgment. This is the real audience, and it should drive prioritization — polish and defensibility of the *reasoning*, not breadth of financial coverage, is what will actually be evaluated.
**Is the value proposition compelling?** As a resume/portfolio artifact: yes — the deliberate separation of deterministic and probabilistic workloads, explicit refusal behavior, and an evaluation harness are genuinely above what most "chat with my PDF" clones do. As a standalone product idea: no differentiated value proposition — everything in the design already exists, often better-resourced, in the incumbent tools above.
 
---
 
## 2. Architecture Evaluation (as documented, not redesigned)
 
**Strengths**
- AD-007 (dashboard reads only `structured_financials`, chat reads only `chunks`, never joined) is the single best decision in the whole document set. It's a real production pattern, not just a talking point, and it directly prevents the most damaging failure mode (a hallucinated ratio presented as fact).
- Hybrid retrieval (BM25 + pgvector + RRF) followed by cross-encoder reranking, restricted to reranking only the retrieved top-K, matches current best practice for keyword-sensitive domains like finance (tickers, "EBITDA," "Item 7" are exactly where vector-only retrieval fails).
- Explicit refusal + a *hard* retry cap (2) is a correct, disciplined choice — the docs' own reasoning ("prevents runaway loops") is sound.
- Mandatory, denormalized chunk metadata (ticker, fiscal_year, item_number, chunk_type, etc.) is what actually makes SQL-filtered vector search useful; this is often skipped in weekend RAG builds and its inclusion here is a genuine strength.
- Observability (Langfuse) and a CI faithfulness gate are unusually mature for a pre-code project.
**Weaknesses**
- The two most consequential technical decisions — embedding model and LLM — are still open, despite the architecture being labeled "Final accepted architecture." An architecture that can't yet answer "what generates the answer" isn't fully locked yet, regardless of the status header.
- The 8-node LangGraph topology is arguably more machinery than the stated traffic (~50 queries/month) needs. That's a defensible portfolio choice, but the docs themselves flag LangGraph's async conditional-edge logic as "a known source of subtle bugs," and admit node-isolation testing "not yet practiced, since no code exists." Complexity here is a deliberate signal-vs-risk trade, not a free win.
- **The largest gap:** the `structured_financials` extraction pipeline is designed to reconstruct data via Docling parsing + a custom extractor from PDF tables — but the SEC already publishes every GAAP-tagged line item as free, machine-readable, issuer-attested XBRL JSON via `data.sec.gov`, requiring no PDF parsing at all<cite index="22-1">XBRL financial facts are machine-readable, time-stamped, and directly comparable across companies</cite>, with a documented API that <cite index="26-1">offers submissions history by filer and extracted XBRL data from financial statements in JSON format</cite>. Building a bespoke table-extraction path to reproduce data the filer has already structured and certified is the single biggest unforced risk in a system whose #1 hard constraint is "never guess a financial number."
**Assumptions the architecture depends on**
1. Docling will reliably parse real 10-K tables — the docs themselves call this "untested... as of this writing," and independent benchmarks are far less uniform than the cited 94%-vs-45% comparison suggests (see Section 7).
2. RAGAS faithfulness scores are a trustworthy proxy for real answer correctness — research suggests this correlation is only moderate, not the near-certainty a hard CI gate implies (see Section 6/7).
3. Supabase's free tier stays viable and "warm" between recruiter visits.
4. GPT-4o-mini remains available and cheap through the build — it is actively being retired across OpenAI's product surface in 2026 (see Section 5).
---
 
## 3. Technical Feasibility
 
- **Single-filing prototype (Phase 1 gate):** realistic. Docling, FastAPI, and a hierarchical chunker on one document is a well-bounded, achievable scope.
- **Reliable table extraction across varied filings:** the hardest part of the whole system, and genuinely hard industry-wide — merged cells, multi-page tables, and restated figures are exactly where even funded platforms struggle, which is why dedicated research benchmarks (PHANTOM, FAITH, Fin-RATE) exist specifically to measure numerical/tabular hallucination in financial QA rather than treating it as solved.
- **Answer quality under FinanceBench-style scrutiny:** sobering historically — early open-book financial QA evaluation found that <cite index="20-1">even GPT-4-Turbo with retrieval incorrectly answered or refused to answer 81% of questions</cite> on FinanceBench, and more recent professional-task benchmarks still find <cite index="20-1">current LLMs fail approximately 60% of such tasks</cite>. Newer frontier models score much higher on aggregate finance benchmarks, but that's precisely why the project's refusal-first design is the right instinct — it's compensating for a documented, persistent weakness rather than assuming the problem is solved.
- **Latency:** the full graph (optional HyDE roundtrip → parallel BM25/vector → RRF → cross-encoder rerank at ~100–200ms → generation → hallucination guard → up to 2 retries) means several sequential LLM calls per answer in the worst case. Fine at demo scale, but worth setting expectations — this will not feel "instant."
- **Solo/fresher build complexity:** eight LangGraph nodes, a three-level chunker, a separate structured extractor, hybrid retrieval, reranking, a hallucination guard, RAGAS+Langfuse+CI, and a two-platform deployment is a large surface for one person to ship pre-interview-season. The project's own three memory files (each independently "reconciled," none yet with code) is itself a mild warning sign of extended design-phase drift.
---
 
## 4. Industry Comparison
 
*(Financial-document intelligence, the actually relevant category — not legal contract review.)*
 
| | Ask My Filings | AlphaSense / Hebbia | Fintool / Daloopa | EDGAR-native tools (Calcbench, Workiva) |
|---|---|---|---|---|
| Data source | User-uploaded PDF only | Aggregated multi-source library (filings, broker research, expert calls via Tegus) | Filings + XBRL, narrower scope | Live EDGAR/API connection |
| Structured extraction | Custom PDF-table extractor (unbuilt) | Enterprise data pipelines | <cite index="5-1">XBRL-to-table mapping that extracts financial line items into clean tables, identifying and reconciling period-over-period mapping changes</cite> | Direct XBRL ingestion |
| Freshness | Manual upload only | Near real-time | Near real-time | <cite index="7-1">Ingest filings at or near publication</cite> |
| Refusal / grounding | Explicit refusal node (strong) | Evidence-linked citations, but breadth over precision | Precision-focused, narrow lane | Enterprise-grade, audited |
 
**Where the project is stronger:** the deterministic/probabilistic separation (AD-007) is a cleaner architectural discipline than most consumer-facing tools bother to expose; the explicit refusal-first design is well ahead of "confident chatbot" competitors.
 
**Where it's weaker:** no live EDGAR connection, no XBRL usage, single-document scope, and the exact reconciliation step Fintool already ships (<cite index="5-1">identifying and reconciling period-over-period mapping changes that traditional scrapers miss</cite>) is listed in this project's own docs as an unimplemented "open gap."
 
**Where legal-AI patterns are actually relevant:** citation-enforced generation with a hard refusal path on low-confidence retrieval is now the standard shape for *any* high-stakes document-AI system — contract-review tools use the same pattern for the same reason. That means this architecture isn't unusual; it's correctly following the now-standard playbook for regulated-document RAG. The differentiator for a portfolio reviewer will be execution depth, not the pattern itself.
 
---
 
## 5. Alternative Approaches
 
**1. Use SEC's free XBRL company-facts API as the primary source for `structured_financials`, keep Docling only for narrative/table chunking (not ratio extraction).**
- Why superior: near-zero-cost, issuer-attested, machine-readable data for every GAAP-tagged line item — removes the single largest correctness risk from the most safety-critical part of the system (Hard Constraint #1).
- Trade-off: doesn't eliminate Docling — narrative sections (Item 1A risk factors, Item 7 MD&A) still need structure-aware parsing for the chat workload. This is additive, not a replacement.
- Migration difficulty: low. It's a new ingestion branch feeding the same `structured_financials` table; no schema change, and it can be added before the Phase 1 gate without disrupting anything already decided.
**2. Re-open the LLM decision now, rather than defaulting to GPT-4o-mini.**
- Why: GPT-4o-mini is actively being sunset across OpenAI's surfaces in 2026 — ChatGPT access to GPT-4o was retired February 13, 2026, and <cite index="54-1">the gpt-4o-mini model has a retirement date of March 31, 2026</cite> on Azure deployments, with the broader GPT-4 line being consolidated toward the GPT-5 family. Locking in a model mid-retirement creates avoidable rework.
- Trade-off: candidates (GPT-5-mini/nano, Claude Haiku 4.5, Gemini Flash) all need a fresh cost/quality pass, which the docs already correctly flag as an open decision requiring a real recommendation, not a silent pick.
- Migration difficulty: trivial now (zero code exists); expensive later (after prompts/evals are tuned to one model's quirks).
**3. Build a minimal 3-node graph first (Classify → Retrieve/Generate → Refuse), then layer in HyDE/Reranker/Retry exactly as Phase 4 already schedules.**
- Why: gets an end-to-end, demoable system alive faster, directly addressing the docs' own admitted risk that LangGraph node behavior "not yet practiced" in isolation.
- Trade-off: none really — this is the existing phase roadmap, just a discipline reminder not to build all 8 nodes before anything runs end-to-end.
- Migration difficulty: none — this is sequencing, not a design change.
---
 
## 6. Major Pitfalls
 
- **Technical:** untested Docling performance on real, complex 10-K tables (multi-page, merged headers); LangGraph conditional-edge bugs (self-flagged); latency stacking from HyDE + rerank + retries; Supabase free-tier cold-starts undermining a "live demo."
- **Product:** the real risk isn't scope, it's *finishing* — three separately-reconciled memory documents and zero code is a pattern seen in stalled portfolio projects generally.
- **Data quality:** unit confusion (thousands vs. millions) and period confusion (prior-year vs. current-year) are not hypothetical — they're the specific failure mode multiple 2025–2026 papers were built to measure (PHANTOM for long-context hallucination, FAITH for "intrinsic tabular hallucinations in finance").
- **Legal/compliance:** low real risk for a portfolio demo, but a visible "not investment advice" disclaimer is cheap insurance; redistributing/hosting filing PDFs at scale should stay within SEC's EDGAR access norms (rate limits, identifying User-Agent) even though the underlying filings are public records.
- **Evaluation/benchmarking:** RAGAS's faithfulness metric is LLM-graded, and independent work has found <cite index="43-1">correlation between RAGAS metrics and human evaluation yields a harmonic mean of only 0.55</cite> — a hard CI gate at 0.85 faithfulness gives more confidence than the underlying metric actually supports unless paired with real human-reviewed spot checks.
- **Long-term maintenance:** the golden test set and pinned model choices both go stale quickly in a fast-moving space — the GPT-4o-mini deprecation timeline found in this review is a concrete example of exactly that risk materializing.
---
 
## 7. Hidden Risks (less obvious from the docs alone)
 
- **The 94%-vs-45% Docling comparison is directional, not universal.** Independent 2025–2026 benchmarks show real spread by document type and evaluator: one benchmark found <cite index="31-1">Docling's deep learning layout model correctly identified table boundaries, column alignment, and cell spanning in 97.9% of test cases</cite>, while a separate invoice-extraction study found Docling scoring only 63% overall accuracy against a competing tool's 94% on that specific task type. Treat the cited figure as "Docling beats naive text-flattening parsers," not "Docling will hit 94%+ on this project's actual filings" — which the project's own risk log already implicitly acknowledges by calling it untested.
- **Judge/generator overlap risk:** if a similarly-priced budget model both answers questions and grades faithfulness in RAGAS, the LLM-judge literature's documented self-enhancement and verbosity biases can quietly inflate the exact safety numbers the CI gate depends on. Use a different (ideally stronger) model for grading than for generation.
- **A finance-literate interviewer will very likely ask "why not just use the XBRL API?"** — this is close to a guaranteed question given how well-known and free that data source is in this space, and answering it well (or better, having actually integrated it) is higher-leverage than most of the retrieval sophistication currently planned.
- **The deterministic dashboard can't explain itself in chat** — because chunks and structured_financials are deliberately never joined (correctly, for correctness reasons), there's no natural path for a user to ask "why is this P/E number what it is" without either breaking the separation or building a second, still-deterministic explanation layer. Worth deciding now rather than discovering it during Phase 3.
---
 
## 8. Architecture Consistency Check
 
- **No major contradictions** across the three memory files — genuinely well reconciled. The Neon→Supabase and Streamlit→React pivots, and the `structured_financials` naming conflict, are documented identically and consistently in all three conflict logs. This is unusually disciplined for a pre-code project.
- **Minor date inconsistency:** ARCHITECTURE.md and TECH_DECISIONS.md say "Last reconciled: 2026-08-11"; PROJECT_MEMORY.md says "2026-08-10." Since each file separately claims to supersede prior versions, it's worth confirming which was actually edited most recently before treating any one as the tiebreaker.
- **A real contradiction worth flagging:** the active project instructions list the LLM as part of the "Tech Stack — Locked" section (with only "upgradeable" noted for embeddings), while all three memory files explicitly and repeatedly list the LLM as an *open, unresolved* decision that "blocks Phase 2" and must not be silently defaulted. Those two sources disagree on lock status for the same decision — worth resolving explicitly rather than letting the "locked" framing silently override the memory files' own instruction not to treat it as settled.
- **Under-weighted gap:** reconciliation validation for `structured_financials` (checking that extracted balance-sheet totals actually sum correctly) is filed as an "open architectural gap," but it directly serves Hard Constraint #1 (never present a guessed number as fact) — it reads more like a Phase 1 requirement than a footnote, given what it's protecting against.
---
 
## 9. Success Probability Assessment
 
| Milestone | Probability | Reasoning |
|---|---|---|
| **Working prototype** (one filing, manual-inspection gate) | High (70–85%) | Scope is well-bounded, all chosen tools are mainstream and documented, and the phase-gate criteria are concrete and testable. |
| **MVP** (multiple filings, working chat + dashboard, deployed) | Moderate (35–50%) | Table-parsing reliability across varied real-world filings, LangGraph debugging surface, and solo-builder attrition risk between "architecture finalized" and "shipped" are the real friction points — not any single technical choice. |
| **Production-ready system** (real users, SLAs, compliance review) | Low (<10%) | Not actually the stated goal, and reaching it would require legal review, XBRL-grade reconciliation, and probably trading away some of the more elaborate machinery for operational simplicity. This is fine — explicitly out of scope for a recruiter-facing portfolio piece. |
 
---
 
## 10. Final Recommendation
 
**Proceed as designed, with two changes made before any code is written:**
 
1. **Add SEC's free XBRL company-facts API as the primary source for `structured_financials`**, keeping Docling for narrative/table chunking only. This is the single highest-leverage change available — it removes the largest correctness risk from the most safety-critical part of the system, closes the "why not just use XBRL" interview question preemptively, and is additive (low migration cost, no schema change).
2. **Re-open and lock the LLM decision now.** GPT-4o-mini is mid-retirement across OpenAI's product surfaces in 2026; picking a currently-supported budget model (GPT-5-mini/nano, Claude Haiku 4.5, or Gemini Flash, evaluated head-to-head as the docs already call for) avoids building tuned prompts and evals around a model that may not be available by the time the project ships.
**Don't simplify the RAG/LangGraph architecture** — it's sound and it's good signal; the risk here isn't over-design, it's under-shipping. Build the minimal 3-node path first (classify → retrieve/generate → refuse) to get something end-to-end and demoable, then layer in HyDE, reranking, and retry logic exactly per the existing Phase 4 plan — this is really just a sequencing discipline reminder, not a change to the roadmap already written.
 
**Promote reconciliation validation on `structured_financials`** from an "open gap" to an explicit Phase 1 requirement, since it directly protects the project's own Hard Constraint #1.
 
---
 
### Sources consulted
- IntuitionLabs, *LLMs for Financial Document Analysis: SEC Filings & Decks* (2026)
- Hebbia, *Top 10 AlphaSense Competitors* and *Top 12 AI Financial Research Platforms* (2026)
- Finrep, *AI Tools for SEC Filing Research Compared: 2026 Guide*
- Islam et al., *FinanceBench: A New Benchmark for Financial Question Answering* (arXiv:2311.11944)
- *PHANTOM: A Benchmark for Hallucination Detection in Financial Long-Context QA* (NeurIPS 2025)
- *FAITH: A Framework for Assessing Intrinsic Tabular Hallucinations in Finance* (ICAIF 2025)
- Apify / sec-api.io / SEC.gov Developer Resources — EDGAR XBRL structured data APIs
- Ertas AI, *PDF Parsing Accuracy Benchmark: Docling vs Unstructured vs Marker* (2026); arXiv:2510.15727 (Docling vs. LlamaExtractor on invoices)
- *RIKER and the Coherent Simulated Universe* (arXiv:2601.08847) — RAGAS/human correlation study
- OpenAI, *Retiring GPT-4o and other ChatGPT models*; Microsoft Q&A on Azure Foundry GPT-4o-mini retirement (2026)