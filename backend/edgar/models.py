"""Pydantic response models for SEC EDGAR data (Phase 1, Session 3).

These models intentionally mirror SEC's raw JSON structure — no reshaping
into a custom schema here. Downstream consumers (e.g. Phase 3's
``xbrl/concept_map.py``) are written against SEC's real key names.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CikEntry(BaseModel):
    """A single (ticker, CIK, title) entry from SEC's company_tickers.json."""

    cik: str
    ticker: str
    title: str


class SubmissionsResponse(BaseModel):
    """Top-level structure of https://data.sec.gov/submissions/CIK{cik}.json.

    ``filings`` keeps SEC's raw ``filings`` dict (including the ``recent``
    array) as-is; the XBRL normalizer in Phase 3 consumes company-facts, not
    submissions, so over-modeling here is deliberately avoided.
    """

    cik: str
    name: str
    sic: str | None = None
    filings: dict[str, Any]