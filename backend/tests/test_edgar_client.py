"""Tests for the SEC EDGAR client (Phase 1, Session 3).

All HTTP traffic is mocked with httpx.MockTransport so the suite is fully
deterministic and requires no network access and no SEC_EDGAR_USER_AGENT
value of the developer's own.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault(
    "SEC_EDGAR_USER_AGENT", "ask-my-filings-test contact@example.com"
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

import edgar.client as edgar_client

assert edgar_client.USER_AGENT == os.environ["SEC_EDGAR_USER_AGENT"]

COMPANY_TICKERS_SAMPLE: dict[str, dict[str, object]] = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    "2": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
}

SUBMISSIONS_APPLE: dict[str, object] = {
    "cik": "0000320193",
    "name": "Apple Inc.",
    "sic": "3571",
    "filings": {
        "recent": {
            "accessionNumber": ["0000320193-25-000123"],
            "form": ["10-K"],
            "filingDate": ["2025-11-05"],
        },
        "files": [],
    },
}


def _json_response(status_code: int, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=payload, request=None)


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch):
    """Point the client's shared HTTP client at an httpx.MockTransport.

    Returns a callable ``install(handler)`` that records every request made
    and returns the list of calls so tests can assert on them.
    """

    def install(handler) -> list[httpx.Request]:
        calls: list[httpx.Request] = []

        def recording_handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return handler(request)

        def factory() -> httpx.Client:
            return httpx.Client(
                transport=httpx.MockTransport(recording_handler),
                headers={"User-Agent": edgar_client.USER_AGENT},
            )

        monkeypatch.setattr(edgar_client, "_build_http_client", factory)
        monkeypatch.setattr(edgar_client, "_http_client", None)
        return calls

    return install


def test_resolve_cik_apple(mock_http) -> None:
    calls = mock_http(
        lambda request: _json_response(200, COMPANY_TICKERS_SAMPLE)
    )

    assert edgar_client.resolve_cik("AAPL") == "0000320193"
    assert edgar_client.resolve_cik("aapl") == "0000320193"

    assert len(calls) == 2
    assert calls[0].url == edgar_client.COMPANY_TICKERS_URL
    assert calls[0].headers["User-Agent"] == edgar_client.USER_AGENT


def test_resolve_cik_unknown_ticker_raises(mock_http) -> None:
    mock_http(lambda request: _json_response(200, COMPANY_TICKERS_SAMPLE))

    with pytest.raises(ValueError, match="not found"):
        edgar_client.resolve_cik("ZZZZ")

    with pytest.raises(ValueError, match="ticker must not be empty"):
        edgar_client.resolve_cik("")


def test_get_submissions_apple(mock_http) -> None:
    calls = mock_http(lambda request: _json_response(200, SUBMISSIONS_APPLE))

    submissions = edgar_client.get_submissions("320193")

    assert submissions.name == "Apple Inc."
    assert submissions.cik == "0000320193"
    assert submissions.sic == "3571"
    assert submissions.filings["recent"]["form"] == ["10-K"]

    assert str(calls[0].url) == "https://data.sec.gov/submissions/CIK0000320193.json"
    assert calls[0].headers["User-Agent"] == edgar_client.USER_AGENT


def test_rate_limiter_throttles(mock_http) -> None:
    n = edgar_client.RATE_LIMIT
    calls = mock_http(lambda request: _json_response(200, COMPANY_TICKERS_SAMPLE))

    start = time.monotonic()
    for _ in range(n):
        edgar_client.resolve_cik("AAPL")
    elapsed = time.monotonic() - start

    assert len(calls) == n
    assert elapsed >= n / edgar_client.RATE_LIMIT


def test_backoff_on_429(mock_http, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(edgar_client, "BACKOFF_BASE_SECONDS", 0.01)
    sleeps: list[float] = []
    monkeypatch.setattr(edgar_client, "_sleep", sleeps.append)

    statuses = iter([429, 429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        code = next(statuses)
        payload = SUBMISSIONS_APPLE if code == 200 else {}
        return _json_response(code, payload)

    calls = mock_http(handler)

    submissions = edgar_client.get_submissions("0000320193")

    assert len(calls) == 3
    assert [call.url for call in calls] == [calls[0].url] * 3
    assert submissions.name == "Apple Inc."
    assert 0.01 in sleeps
    assert 0.02 in sleeps


def test_retries_exhausted_raises(mock_http, monkeypatch) -> None:
    """All 3 retries fail (429 x4 total) -> EdgarRequestError, 4 calls made."""
    monkeypatch.setattr(edgar_client, "BACKOFF_BASE_SECONDS", 0.01)
    calls = mock_http(lambda request: _json_response(429, {}))

    with pytest.raises(edgar_client.EdgarRequestError):
        edgar_client.get_submissions("0000320193")

    assert len(calls) == 4  # initial + 3 retries


def test_non_retryable_status_raises(mock_http) -> None:
    """404 -> immediate EdgarRequestError, exactly 1 call, no retries."""
    calls = mock_http(lambda request: _json_response(404, {}))

    with pytest.raises(edgar_client.EdgarRequestError):
        edgar_client.get_submissions("0000320193")

    assert len(calls) == 1


def test_malformed_payload_raises_wrapped(mock_http) -> None:
    """filings present but wrong type -> ValidationError wrapped as
    EdgarRequestError, not a raw pydantic exception."""
    payload = {**SUBMISSIONS_APPLE, "filings": ["not", "a", "dict"]}
    calls = mock_http(lambda request: _json_response(200, payload))

    with pytest.raises(edgar_client.EdgarRequestError):
        edgar_client.get_submissions("0000320193")

    assert len(calls) == 1