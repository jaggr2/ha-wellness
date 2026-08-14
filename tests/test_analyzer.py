"""Unit tests for the Groq meal-analysis helpers."""

from __future__ import annotations

from loader import load_module

analyzer = load_module("analyzer", "analyzer.py")


def test_parse_analysis_plain_json():
    text = (
        '{"food":[{"item":"Pasta","amount":250,"amount_unit":"g","confidence":0.9}],'
        '"beverages":[{"item":"Water","amount":300,"amount_unit":"ml","confidence":0.95}],'
        '"estimated_kcal_total":420,'
        '"estimated_kcal_per_item":[{"item":"Pasta","kcal":420}],'
        '"notes":"Lunch"}'
    )
    result = analyzer.parse_analysis(text)
    assert result["food"][0]["item"] == "Pasta"
    assert result["food"][0]["amount"] == 250
    assert result["beverages"][0]["amount"] == 300
    assert result["estimated_kcal_total"] == 420
    assert result["estimated_kcal_per_item"][0]["kcal"] == 420


def test_parse_analysis_markdown_fences():
    text = '```json\n{"food":[],"beverages":[],"estimated_kcal_total":0,"estimated_kcal_per_item":[],"notes":""}\n```'
    result = analyzer.parse_analysis(text)
    assert result["estimated_kcal_total"] == 0
    assert result["food"] == []


def test_parse_analysis_unparseable():
    result = analyzer.parse_analysis("I see a plate of pasta.")
    assert result["error"] == "unparseable"


def test_parse_analysis_normalizes_types():
    text = (
        '{"food":[{"item":"Apple","amount":"1","amount_unit":"x","confidence":"0.8"}],'
        '"estimated_kcal_total":"95",'
        '"estimated_kcal_per_item":[{"item":"Apple","kcal":"95"}]}'
    )
    result = analyzer.parse_analysis(text)
    assert result["food"][0]["amount"] == 1.0
    assert result["food"][0]["confidence"] == 0.8
    assert result["estimated_kcal_total"] == 95.0
    assert result["estimated_kcal_per_item"][0]["kcal"] == 95.0


def test_image_url_data():
    data = analyzer.image_url_data(b"\xff\xd8\xff")
    assert data.startswith("data:image/jpeg;base64,")
    assert analyzer.image_url_data(b"\xff", "image/png").startswith("data:image/png;base64,")
