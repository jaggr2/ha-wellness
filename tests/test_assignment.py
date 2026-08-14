"""Unit tests for the smart-scale assignment helpers."""

from __future__ import annotations

import pytest

from loader import load_module

assignment = load_module("assignment", "assignment.py")

NOW = 1_750_000_000.0
DAY = 86400.0


def test_assign_single_candidate():
    history = {"roger": (84.0, NOW - DAY * 2), "partner": (62.0, NOW - DAY * 2)}
    result, target = assignment.find_assignee(84.5, history, now=NOW)
    assert result == "assign"
    assert target == "roger"


def test_ask_on_multiple_candidates():
    history = {"roger": (84.0, NOW - DAY), "partner": (62.0, NOW - DAY)}
    # 84.0 is within 5 kg of both only if partner near... use two close weights
    history = {"roger": (84.0, NOW - DAY), "partner": (83.0, NOW - DAY)}
    result, candidates = assignment.find_assignee(84.2, history, now=NOW)
    assert result == "ask"
    assert set(candidates) == {"roger", "partner"}


def test_ask_on_no_candidates():
    history = {"roger": (84.0, NOW - DAY)}
    result, candidates = assignment.find_assignee(95.0, history, now=NOW)
    assert result == "ask"
    assert candidates == []


def test_stale_history_is_not_a_candidate():
    history = {"roger": (84.0, NOW - 100 * DAY)}  # > 60 days old
    result, candidates = assignment.find_assignee(84.5, history, now=NOW)
    assert result == "ask"
    assert candidates == []


def test_delta_boundary():
    history = {"roger": (84.0, NOW - DAY)}
    assert assignment.find_assignee(89.0, history, max_delta=5.0, now=NOW)[0] == "assign"
    assert assignment.find_assignee(89.1, history, max_delta=5.0, now=NOW)[0] == "ask"


def test_should_ignore_repeat():
    assert assignment.should_ignore(84.5, 84.5, NOW, now=NOW) is True
    assert assignment.should_ignore(84.5, 84.0, NOW, now=NOW) is False
    assert assignment.should_ignore(84.5, 84.5, NOW - 1000, now=NOW) is False
    assert assignment.should_ignore(84.5, None, None, now=NOW) is False


def test_to_kg_grams():
    assert assignment.to_kg(118_000, "g") == 118.0
    assert assignment.to_kg(118_000, "G") == 118.0


def test_to_kg_kilograms_identity():
    assert assignment.to_kg(84.5, "kg") == 84.5


def test_to_kg_pounds():
    assert assignment.to_kg(84.5, "lb") == pytest.approx(84.5 * 0.45359237)


def test_to_kg_unknown_unit_passthrough():
    assert assignment.to_kg(84.5, "custom_unit") == 84.5
    assert assignment.to_kg(84.5, None) == 84.5


def test_assignee_with_gram_reading():
    history = {"roger": (118.0, NOW - DAY), "derog_ha": (62.0, NOW - DAY)}
    result, target = assignment.find_assignee(assignment.to_kg(117_800, "g"), history, now=NOW)
    assert result == "assign"
    assert target == "roger"
