"""
backend/db/test_connection.py

Phase 0 connectivity check for the Ask My Filings Supabase project.

Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the repo-root .env,
creates a Supabase client, validates the configuration, and performs a
read-only round trip against the PostgREST root endpoint (/rest/v1/) to
confirm the project is reachable and the credentials are accepted.

This script never creates tables, never runs migrations, and never modifies
the Supabase project in any way. It is a pure connectivity + credential check.

Usage:
    python backend/db/test_connection.py
"""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from supabase import Client, create_client

# The script lives at backend/db/, so the repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = REPO_ROOT / ".env"

# PostgREST root endpoint is a static OpenAPI document — safe, read-only.
POSTGREST_ROOT = "/rest/v1/"
REQUEST_TIMEOUT_SECONDS = 15.0


def load_env() -> None:
    """Load the repo-root .env file (gitignored — real values are never committed)."""
    if not ENV_PATH.exists():
        print(f"[FAIL] .env not found at {ENV_PATH}")
        print("Copy .env.example to .env and populate SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY first.")
        sys.exit(1)
    load_dotenv(ENV_PATH, override=False)


def validate_config() -> tuple[str, str]:
    """Read and validate the two required environment variables. Exits on failure."""
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    errors: list[str] = []
    if not supabase_url:
        errors.append("SUPABASE_URL is missing or empty in .env")
    elif not supabase_url.startswith("https://"):
        errors.append("SUPABASE_URL must be an https:// URL")

    if not service_role_key:
        errors.append("SUPABASE_SERVICE_ROLE_KEY is missing or empty in .env")

    if errors:
        print("[FAIL] Configuration validation failed:")
        for error in errors:
            print(f"  - {error}")
        print("Fix .env and re-run. See .env.example for the expected keys.")
        sys.exit(1)

    print("[OK] Configuration loaded from .env")
    print(f"  SUPABASE_URL: {supabase_url}")
    print(f"  SUPABASE_SERVICE_ROLE_KEY: set ({len(service_role_key)} characters)")
    return supabase_url, service_role_key


def check_connectivity(supabase_url: str, service_role_key: str) -> None:
    """
    Perform a read-only round trip against PostgREST.

    GET /rest/v1/ returns the OpenAPI document (HTTP 200) when the project is
    reachable and the credentials are accepted. It touches no tables or rows,
    so it satisfies the "do not modify Supabase" constraint.
    """
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    try:
        response = httpx.get(
            f"{supabase_url.rstrip('/')}{POSTGREST_ROOT}",
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        print(f"[FAIL] Network error while contacting Supabase: {exc}")
        sys.exit(1)

    if response.status_code == 200:
        print("[OK] Connectivity verified — Supabase accepted the request (HTTP 200)")
        return

    print(f"[FAIL] Connectivity check failed — HTTP {response.status_code}")
    print(f"  Response body: {response.text[:200]}")
    if response.status_code == 401:
        print("  The service role key was rejected. Verify SUPABASE_SERVICE_ROLE_KEY in .env.")
    sys.exit(1)


def main() -> None:
    print("Ask My Filings — Supabase connectivity test (Phase 0)")
    print("-" * 60)

    load_env()
    supabase_url, service_role_key = validate_config()

    try:
        supabase: Client = create_client(supabase_url, service_role_key)
        print("[OK] Supabase client created")
    except Exception as exc:  # noqa: BLE001 — surface any client-construction failure
        print(f"[FAIL] Could not create Supabase client: {exc}")
        sys.exit(1)

    check_connectivity(supabase_url, service_role_key)
    print("-" * 60)
    print("Success — no tables created, no migrations run, no changes made to Supabase.")


if __name__ == "__main__":
    main()