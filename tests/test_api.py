"""HTTP layer: response shape, decimal strings, date validation, page labels."""

import pytest
from fastapi.testclient import TestClient

from app import main
from tests.support import entry, ledger_with, line

client = TestClient(main.app)


def get_json(start, end):
    return client.get("/income-statement", params={"start": start, "end": end})


def test_q1_json():
    response = get_json("2026-01-01", "2026-03-31")
    assert response.status_code == 200
    body = response.json()
    assert body["net_income"] == "-44480.14"  # a string, not a float
    assert body["gross_profit"] == "23577.75" and body["operating_income"] == "-44522.32"
    revenue = body["sections"][0]
    assert revenue["key"] == "revenue" and revenue["total"] == "37850.50"
    assert [a["amount"] for a in revenue["accounts"]] == ["35650.75", "3000.00", "-800.25"]


def test_zero_amounts_serialize_with_two_decimals():
    body = get_json("2026-02-01", "2026-02-28").json()
    other_income = body["sections"][3]
    assert other_income["total"] == "0.00" and other_income["accounts"][0]["amount"] == "0.00"


def test_single_day_range_is_valid():
    assert get_json("2026-03-31", "2026-03-31").status_code == 200


def test_extreme_range_equals_all_time():
    body = get_json("0001-01-01", "9999-12-31").json()
    assert body["net_income"] == "-30380.14"


@pytest.mark.parametrize(
    "params",
    [
        {"end": "2026-03-31"},
        {"start": "2026-01-01"},
        {"start": "", "end": "2026-03-31"},
        {"start": "2026-02-30", "end": "2026-03-31"},
        {"start": "2026-13-01", "end": "2026-03-31"},
        {"start": "01/31/2026", "end": "2026-03-31"},
        {"start": "2026-1-5", "end": "2026-03-31"},
        {"start": "yesterday", "end": "2026-03-31"},
        {"start": "1767225600", "end": "2026-03-31"},
        {"start": "20260101", "end": "2026-03-31"},
        {"start": "2026-01-01 ", "end": "2026-03-31"},
        {"start": "2026-01-01", "end": "2026-03-31T00:00:00"},
    ],
)
def test_bad_dates_are_422(params):
    response = client.get("/income-statement", params=params)
    assert response.status_code == 422 and response.json()["detail"]


def test_start_after_end_is_422_with_reason():
    response = get_json("2026-03-31", "2026-01-01")
    assert response.status_code == 422
    assert response.json()["detail"] == "start must be on or before end."
