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


def test_rewrite_jsonl_removes_matching(tmp_path):
    path = str(tmp_path / "meal-log.jsonl")
    ledger.append_jsonl(path, {"ts": "t1", "photo": "food-photos/a.jpg", "source": "ha-app"})
    ledger.append_jsonl(path, {"ts": "t2", "photo": "food-photos/b.jpg", "source": "ha-app"})
    removed = ledger.rewrite_jsonl(path, lambda r: r["photo"] != "food-photos/a.jpg")
    assert removed == 1
    lines = [json.loads(l) for l in open(path, encoding="utf-8")]
    assert [l["photo"] for l in lines] == ["food-photos/b.jpg"]


def test_rewrite_jsonl_missing_file(tmp_path):
    assert ledger.rewrite_jsonl(str(tmp_path / "nope.jsonl"), lambda r: True) == 0


def test_delete_photo(tmp_path):
    p = tmp_path / "img.jpg"
    p.write_bytes(b"123")
    assert ledger.delete_photo(str(p)) is True
    assert not p.exists()
    assert ledger.delete_photo(str(p)) is False


def test_eating_regularity_empty():
    r = ledger.eating_regularity([], now=1000.0, today_start_epoch=0.0)
    assert r["meals_today"] == 0
    assert r["min_gap_min"] is None
    assert r["too_frequent"] is False


def test_eating_regularity_gaps():
    now = 13 * 3600.0  # 13:00 local-ish epoch
    today_start = 0.0
    # meals at 08:00, 09:30, 12:00 -> gaps 90 and 150 minutes
    times = [8 * 3600.0, 9.5 * 3600.0, 12 * 3600.0]
    r = ledger.eating_regularity(times, now=now, today_start_epoch=today_start)
    assert r["meals_today"] == 3
    assert r["min_gap_min"] == 90.0
    assert r["avg_gap_min"] == 120.0
    assert r["last_gap_min"] == 150.0
    assert r["too_frequent"] is True  # 90 < 120 min


def test_eating_regularity_healthy():
    now = 10 * 3600.0
    times = [7 * 3600.0, 10 * 3600.0]  # 3h apart
    r = ledger.eating_regularity(times, now=now, today_start_epoch=0.0)
    assert r["min_gap_min"] == 180.0
    assert r["too_frequent"] is False


def test_eating_regularity_yesterday_excluded():
    now = 10 * 3600.0
    today_start = 5 * 3600.0  # meals before 05:00 count as yesterday
    times = [4 * 3600.0, 8 * 3600.0, 9 * 3600.0]
    r = ledger.eating_regularity(times, now=now, today_start_epoch=today_start)
    assert r["meals_today"] == 2  # 08:00 + 09:00
