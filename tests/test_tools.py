"""
Unit tests for fetch_jobs filtering logic.
Run from repo root: pytest tests/

These tests don't hit Firestore — they only exercise the in-memory job catalog
filter logic. Integration tests live in scripts/02_test_mcp.sh.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp_server"))

from tools import fetch_jobs_impl


def run(coro):
    return asyncio.run(coro)


def test_no_filter_returns_all():
    result = run(fetch_jobs_impl())
    assert result["count"] == 8
    assert len(result["jobs"]) == 8


def test_role_filter_data_analyst():
    result = run(fetch_jobs_impl(role="data analyst"))
    assert result["count"] >= 1
    assert all("data" in (j["role"] + j["title"]).lower() for j in result["jobs"])


def test_location_filter_richmond():
    result = run(fetch_jobs_impl(location="Richmond"))
    assert result["count"] >= 1
    assert all("Richmond" in j["location"] for j in result["jobs"])


def test_keyword_filter_python():
    result = run(fetch_jobs_impl(keyword="python"))
    assert result["count"] >= 2  # Google, Capital One, Anthropic at least


def test_combined_filters():
    result = run(fetch_jobs_impl(location="CA", keyword="swe"))
    assert all("CA" in j["location"] for j in result["jobs"])


def test_no_match():
    result = run(fetch_jobs_impl(role="quantum computing"))
    assert result["count"] == 0
