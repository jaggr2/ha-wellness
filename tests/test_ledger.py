"""Unit tests for the pure ledger helpers."""

from __future__ import annotations

import json

from loader import load_module

ledger = load_module("ledger", "ledger.py")


def test_slugify():
    assert ledger.slugify("Roger") == "roger"
    assert ledger.slugify("Roger M.") == "roger_m"
    assert ledger.slugify("  André Müller ") == "andr_m_ller"
    assert ledger.slugify("!!!") == "user"


def test_unique_slug():
    assert ledger.unique_slug("Roger", set()) == "roger"
    assert ledger.unique_slug("Roger", {"roger"}) == "roger_2"
    assert ledger.unique_slug("Roger", {"roger", "roger_2"}) == "roger_3"


def test_append_and_read(tmp_path):
    path = str(tmp_path / "nested" / "body-metrics-roger.jsonl")
    ledger.append_jsonl(path, {"ts": "t1", "weight_kg": 84.2})
    ledger.append_jsonl(path, {"ts": "t2", "weight_kg": 83.9})
    last = ledger.read_last_line(path)
    assert last["weight_kg"] == 83.9


def test_read_last_line_missing(tmp_path):
    assert ledger.read_last_line(str(tmp_path / "nope.jsonl")) is None


def test_append_body_metrics_dedup(tmp_path):
    path = str(tmp_path / "body-metrics.jsonl")
    row = {"ts": "t1", "weight_kg": 84.2, "waist_cm": 92.0, "source": "manual"}
    assert ledger.append_body_metrics(path, row) is True
    # identical row -> deduped
    assert ledger.append_body_metrics(path, dict(row)) is False
    # changed weight -> appended
    row2 = dict(row, weight_kg=83.9)
    assert ledger.append_body_metrics(path, row2) is True
    lines = [json.loads(l) for l in open(path, encoding="utf-8")]
    assert len(lines) == 2
