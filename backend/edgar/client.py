"""SEC EDGAR HTTP client (Phase 1, Session 3).

Implements CIK resolution and submissions retrieval against SEC's public
EDGAR endpoints, with the SEC-required User-Agent, rate limiting
(8 requests/sec ceiling) and exponential-backoff retries on retryable
status codes (403 / 429 / transient 5xx).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

import httpx
from pydantic import ValidationError

from .models import SubmissionsResponse

_logger = logging.getLogger(__name__)

SEC_SUBMISSIONS_BASE_URL = "https://data.sec.gov/submissions"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_USER_AGENT = os.environ.get("SEC_EDGAR_USER_AGENT")
if not _USER_AGENT:
    raise RuntimeError(
        "SEC_EDGAR_USER_AGENT environment variable must be set to a real "
        "contact (e.g. 'Your Name your@email.com') - SEC rejects EDGAR "
        "requests without a valid User-Agent. See "
        "https://www.sec.gov/os/accessing-edgar-data."
    )
USER_AGENT = _USER_AGENT

RATE_LIMIT = 8  # requests per second ceiling
MAX_RETRIES = 3  # retry attempts after the initial request
BACKOFF_BASE_SECONDS = 1.0  # exponential backoff base
RETRY_STATUS_CODES = frozenset({403, 429, 500, 502, 503, 504})

_sleep: Callable[[float], None] = time.sleep

_http_client: httpx.Client | None = None


class EdgarRequestError(RuntimeError):
    """Raised when an EDGAR request fails after exhausting retries or on a
    non-retryable response. Never returns partial/empty data silently."""


class RateLimiter:
    """Spaces request starts at least ``1/rate`` seconds apart.

    SEC asks for a 10 requests/sec ceiling; the project spec fixes
    ``RATE_LIMIT = 8``. The limiter sleeps before every request (including
    the first), guaranteeing N requests never start faster than N/rate.
    """

    def __init__(self, rate: float) -> None:
        if rate <= 0:
            raise ValueError(f"rate must be positive, got {rate!r}")
        self._interval = 1.0 / rate
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            _sleep(self._interval)


_rate_limiter = RateLimiter(RATE_LIMIT)


def _build_http_client() -> httpx.Client:
    """Create the shared HTTP client. Every request carries the SEC
    User-Agent header — no exceptions."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30.0, connect=10.0),
    )


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = _build_http_client()
    return _http_client


def _normalize_cik(cik: str) -> str:
    """Validate and zero-pad a CIK to the canonical 10-digit form."""
    cik = cik.strip()
    if not cik.isdigit():
        raise ValueError(f"CIK must be numeric, got {cik!r}")
    return cik.zfill(10)


def _request_with_retries(
    method: str,
    url: str,
    cache_key: str | None = None,
    cache_ttl: float | None = None,
) -> httpx.Response:
    """Perform a rate-limited request with exponential-backoff retries.

    Every attempt goes through the rate limiter. Retries on 403/429/transient
    5xx up to ``MAX_RETRIES`` times (backoff = BASE * 2**attempt), then raises
    :class:`EdgarRequestError`. Any other non-2xx raises immediately, no retry.

    ``cache_key`` / ``cache_ttl`` are the Session 4 cache seam: accepted but
    currently unused (no-op) — ``cache.py`` lands in Session 4 and plugs into
    this chokepoint additively, without reworking this function.
    """
    attempt = 0
    while True:
        _rate_limiter.wait()
        try:
            response = _get_http_client().request(method, url)
        except httpx.HTTPError as exc:
            raise EdgarRequestError(
                f"EDGAR {method} {url} failed: {exc}"
            ) from exc
        status = response.status_code

        if status in RETRY_STATUS_CODES and attempt < MAX_RETRIES:
            delay = BACKOFF_BASE_SECONDS * (2**attempt)
            _logger.warning(
                "EDGAR %s %s returned %d; retrying in %.2fs (attempt %d/%d)",
                method,
                url,
                status,
                delay,
                attempt + 1,
                MAX_RETRIES,
            )
            _sleep(delay)
            attempt += 1
            continue

        if status in RETRY_STATUS_CODES:
            _logger.error(
                "EDGAR %s %s failed after %d retries (last status %d)",
                method,
                url,
                MAX_RETRIES,
                status,
            )
            raise EdgarRequestError(
                f"EDGAR {method} {url} failed after {MAX_RETRIES} retries "
                f"(last status {status})"
            )
        if not 200 <= status < 300:
            _logger.error(
                "EDGAR %s %s returned non-retryable status %d",
                method,
                url,
                status,
            )
            raise EdgarRequestError(
                f"EDGAR {method} {url} returned non-retryable status {status}"
            )
        _logger.info("EDGAR %s %s succeeded (status %d)", method, url, status)
        return response


def resolve_cik(ticker: str) -> str:
    """Look up the zero-padded 10-digit CIK for a ticker.

    Uses SEC's company_tickers.json
    (https://www.sec.gov/files/company_tickers.json). Raises
    :class:`ValueError` if the ticker is not found.
    """
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("ticker must not be empty")

    response = _request_with_retries("GET", COMPANY_TICKERS_URL)
    payload: Any = response.json()
    if not isinstance(payload, dict):
        raise EdgarRequestError(
            "company_tickers.json returned an unexpected structure "
            f"(expected a JSON object, got {type(payload).__name__})"
        )

    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("ticker", "")).upper() == normalized:
            cik_str = entry.get("cik_str")
            if cik_str is None:
                raise EdgarRequestError(
                    f"company_tickers.json entry for {normalized!r} is missing 'cik_str'"
                )
            return str(cik_str).zfill(10)

    raise ValueError(f"ticker {ticker!r} not found in SEC company_tickers.json")


def get_submissions(cik: str) -> SubmissionsResponse:
    """Fetch https://data.sec.gov/submissions/CIK{cik}.json."""
    padded_cik = _normalize_cik(cik)
    url = f"{SEC_SUBMISSIONS_BASE_URL}/CIK{padded_cik}.json"
    payload: Any = _request_with_retries("GET", url).json()

    if not isinstance(payload, dict):
        raise EdgarRequestError(
            f"Submissions payload for CIK {padded_cik} is not a JSON object"
        )
    try:
        return SubmissionsResponse(
            cik=padded_cik,
            name=payload["name"],
            sic=payload.get("sic"),
            filings=payload["filings"],
        )
    except (KeyError, TypeError, ValidationError) as exc:
        raise EdgarRequestError(
            f"Submissions payload for CIK {padded_cik} is missing required "
            f"fields: {exc}"
        ) from exc