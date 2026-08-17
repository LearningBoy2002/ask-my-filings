# Phase 1 Spec — SEC EDGAR Client
**Owner:** Claude Account #1 (Architect) — paste this whole file into Account #1's session to log it, then use the OpenCode prompts below as-is.
**Sessions:** 3 (CIK + submissions) and 4 (company-facts + raw filing + rate limiting + caching), per execution plan Part 7.
**Hard Constraints touched:** None directly — this module only fetches raw data. Flag for Account #2: correct CIK zero-padding, correct handling of a 403/429 (must retry with backoff, never silently return empty/None), and User-Agent string must be a real contact (never committed as a placeholder in code — pulled from env only).

---

## Files to create

```
backend/edgar/client.py
backend/edgar/models.py
backend/edgar/cache.py
backend/tests/test_edgar_client.py
```

## Scope boundary
Do not modify any file outside the four listed above. Do not touch `backend/ingestion/`, `backend/xbrl/`, `backend/main.py`, or any file under `docs/`.

---

## `backend/edgar/models.py`

Pydantic models only. No logic.

- `class CikEntry(BaseModel)`: `cik: str`, `ticker: str`, `title: str`
- `class SubmissionsResponse(BaseModel)`: `cik: str`, `name: str`, `sic: str | None`, `filings: dict` (keep raw `recent` filings dict as-is for Phase 1 — don't over-model; Phase 3's XBRL normalizer only needs company-facts, not this)
- `class CompanyFactsResponse(BaseModel)`: `cik: str`, `entity_name: str`, `facts: dict` (raw `us-gaap` / `dei` namespaces preserved as-is; concept mapping happens later in Phase 3's `concept_map.py`, not here)
- `class FilingDocument(BaseModel)`: `accession_number: str`, `filename: str`, `content: bytes`, `content_type: str`

**Note to OpenCode:** do not flatten or reshape SEC's JSON structure into a custom schema here — Phase 3 depends on `facts` being the raw structure SEC returns, since `concept_map.py` is written against real key names.

---

## `backend/edgar/cache.py`

**Assumption stated (Account #1 default, not yet in ARCHITECTURE.md):** no `edgar_cache` table exists in `schema.sql`, and adding one is out of scope for this session. Cache to local disk only for Phase 1: `.cache/edgar/` (gitignored — confirm this path is in `.gitignore`, add if missing).

- `get_cached(key: str) -> bytes | None` — reads `.cache/edgar/{key}.json` or `.cache/edgar/{key}.bin`, returns `None` on miss
- `set_cached(key: str, content: bytes) -> None` — writes to same path, creates dir if missing
- `cache_key(url: str) -> str` — deterministic hash of the URL (e.g. `hashlib.sha256`), used as filename stem

No TTL/expiry logic needed for Phase 1 — filings are immutable once published, so a cache hit is always valid. Flag this assumption to Account #2: confirm it holds even for `submissions.json` (which *does* change as new filings are added) — recommend a short TTL (e.g. 1 hour) specifically for submissions/company-facts endpoints, no TTL for raw filing documents.

---

## `backend/edgar/client.py`

**Constants (from env, never hardcoded):**
- `USER_AGENT = os.environ["SEC_EDGAR_USER_AGENT"]` — fail fast (raise) at import time if unset, don't default to a placeholder string
- `RATE_LIMIT = 8` requests/sec (per execution plan Part 5, Phase 1 row)
- `MAX_RETRIES = 3`, exponential backoff base 1s, only retry on 403/429/5xx

**Functions:**

```python
def resolve_cik(ticker: str) -> str:
    """Look up CIK for a ticker via SEC's company_tickers.json.
    Returns zero-padded 10-digit CIK string (e.g. '0000320193').
    Raises ValueError if ticker not found."""

def get_submissions(cik: str) -> SubmissionsResponse:
    """GET https://data.sec.gov/submissions/CIK{cik}.json"""

def get_company_facts(cik: str) -> CompanyFactsResponse:
    """GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"""

def fetch_filing_document(cik: str, accession_number: str, filename: str) -> FilingDocument:
    """GET https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/{filename}"""
```

**Cross-cutting requirements for every function above:**
- Every request sets `User-Agent: {USER_AGENT}` header — no exceptions
- Every request goes through the rate limiter (8 req/sec ceiling) and the cache (check cache before request, write to cache after a successful response)
- On 403 or 429: exponential backoff retry (max 3 attempts), then raise a clear exception — never return partial/empty data silently
- On any other non-2xx: raise immediately, no retry

---

## `backend/tests/test_edgar_client.py`

Required test cases (Account #2: verify these actually exercise the behavior, not just mock-and-assert-called):

1. `test_resolve_cik_apple` — resolves `AAPL` → `0000320193`
2. `test_resolve_cik_unknown_ticker_raises` — unknown ticker raises `ValueError`
3. `test_get_submissions_apple` — live call, asserts `name` contains "Apple"
4. `test_get_company_facts_apple` — live call, asserts `entity_name` contains "Apple" and `facts` contains `us-gaap` key
5. `test_rate_limiter_throttles` — fires N requests, asserts elapsed time ≥ N/8 seconds
6. `test_backoff_on_429` — mocked response returns 429 twice then 200, asserts 3 calls made and final result returned (not an exception)
7. `test_cache_hit_skips_network` — second call to same URL doesn't hit the network (mock/patch the HTTP client and assert call count == 1)
8. `test_fetch_filing_document_byte_identical` — fetches Apple's `aapl-20250927.htm`, compares against the manually-downloaded ZIP's copy (this is the actual Phase 1 gate criterion — keep this test, don't skip it as "manual only")

---

## Acceptance criteria (must all pass before Session 3/4 gate)

- [ ] `resolve_cik("AAPL")` returns `"0000320193"`
- [ ] `get_submissions` and `get_company_facts` both succeed for Apple's CIK
- [ ] `fetch_filing_document` output is byte-identical to the manually-downloaded ZIP's `aapl-20250927.htm`
- [ ] Repeated test run (run test suite twice back-to-back) produces zero 403s — proves rate limiting + backoff work
- [ ] All 8 tests in `test_edgar_client.py` pass
- [ ] `.cache/edgar/` is gitignored

---

## OpenCode Prompt — Session 3 (CIK resolution + submissions)

```
Implement backend/edgar/client.py and backend/edgar/models.py per this spec:

[paste the "models.py" and "client.py" sections above, plus the two functions
resolve_cik and get_submissions only — omit get_company_facts and
fetch_filing_document for this session]

Requirements:
- User-Agent header pulled from SEC_EDGAR_USER_AGENT env var, fail fast if unset
- Rate limit to 8 req/sec
- Exponential backoff (max 3 retries) on 403/429/5xx only
- Write backend/tests/test_edgar_client.py covering test_resolve_cik_apple,
  test_resolve_cik_unknown_ticker_raises, test_get_submissions_apple,
  test_rate_limiter_throttles, test_backoff_on_429

Do not modify any file outside backend/edgar/client.py, backend/edgar/models.py,
backend/tests/test_edgar_client.py.
```

## OpenCode Prompt — Session 4 (company-facts + raw filing + caching)

```
Extend backend/edgar/client.py with get_company_facts and fetch_filing_document
per this spec, and implement backend/edgar/cache.py:

[paste the "cache.py" section and the remaining two client.py functions from above]

Requirements:
- Local disk cache at .cache/edgar/ (gitignored — add the entry if missing)
- No TTL for raw filing documents; 1-hour TTL for submissions/company-facts responses
- Add test_get_company_facts_apple, test_cache_hit_skips_network,
  test_fetch_filing_document_byte_identical to backend/tests/test_edgar_client.py

Do not modify any file outside backend/edgar/client.py, backend/edgar/cache.py,
backend/tests/test_edgar_client.py, .gitignore.
```

---

## For Account #2 (Reviewer) — priority checks

- [ ] User-Agent is never hardcoded, only read from env
- [ ] CIK padding is correct (10 digits, zero-padded) in every URL built
- [ ] Backoff actually waits between retries (not a busy-loop) and caps at 3 attempts
- [ ] Cache TTL distinction (submissions/company-facts vs. raw filings) is implemented, not just asserted in a comment
- [ ] `test_fetch_filing_document_byte_identical` compares real bytes, not just status code or length
- [ ] No silent swallowing of non-2xx responses anywhere

---

## DECISION_LOG.md entry to add once this session completes

```
2026-08-XX — edgar_client.py: local-disk caching for Phase 1 (.cache/edgar/),
no Supabase edgar_cache table yet — deferred, revisit if caching needs to
survive across deploys/containers. TTL: none for raw filings (immutable),
1hr for submissions/company-facts (mutable).
```
