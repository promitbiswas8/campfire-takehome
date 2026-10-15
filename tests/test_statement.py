"""Accounting tests. Every expected number comes from a hand calculation, not from the app."""

import dataclasses
import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.ledger import load_ledger_file
from app.statement import compute_income_statement
from tests.support import LEDGER_PATH, RAW, entry, ledger_with, line

LEDGER = load_ledger_file(LEDGER_PATH)
PNL_ACCOUNTS = {a["number"] for a in RAW["accounts"] if a["type"] in ("revenue", "expense")}
LEDGER_DATES = sorted({date.fromisoformat(e["date"]) for e in RAW["journal_entries"]})
RANGES = [(start, end) for start in LEDGER_DATES for end in LEDGER_DATES if start <= end]


def statement(start, end, ledger=LEDGER):
    return compute_income_statement(ledger, date.fromisoformat(start), date.fromisoformat(end))


def flatten(result):
    """Every number on the statement, as strings, keyed by account number or total name."""
    numbers = {}
    for section in result.sections:
        for account in section.accounts:
            numbers[account.number] = str(account.amount)
        numbers[section.key] = str(section.total)
    numbers["gross_profit"] = str(result.gross_profit)
    numbers["operating_income"] = str(result.operating_income)
    numbers["net_income"] = str(result.net_income)
    return numbers


def amount(result, number):
    return next(a.amount for s in result.sections for a in s.accounts if a.number == number)


# --- Full statements, pinned to hand calculations -------------------------------------

JANUARY = {
    "4000": "12450.75", "4100": "1000.00", "4900": "0.00", "revenue": "13450.75",
    "5000": "4980.30", "cogs": "4980.30",
    "gross_profit": "8470.45",
    "6000": "18500.00", "6100": "9000.00", "6200": "0.00", "6300": "2500.10",
    "operating_expenses": "30000.10",
    "operating_income": "-21529.65",
    "7000": "0.00", "other_income": "0.00",
    "net_income": "-21529.65",
}
FEBRUARY = {
    "4000": "8200.00", "4100": "1000.00", "4900": "-650.25", "revenue": "8549.75",
    "5000": "3280.00", "cogs": "3280.00",
    "gross_profit": "5269.75",
    "6000": "18500.00", "6100": "0.00", "6200": "0.00", "6300": "0.00",
    "operating_expenses": "18500.00",
    "operating_income": "-13230.25",
    "7000": "0.00", "other_income": "0.00",
    "net_income": "-13230.25",
}
MARCH = {
    "4000": "15000.00", "4100": "1000.00", "4900": "-150.00", "revenue": "15850.00",
    "5000": "6012.45", "cogs": "6012.45",
    "gross_profit": "9837.55",
    "6000": "18500.00", "6100": "0.00", "6200": "1099.97", "6300": "0.00",
    "operating_expenses": "19599.97",
    "operating_income": "-9762.42",
    "7000": "42.18", "other_income": "42.18",
    "net_income": "-9720.24",
}
Q1 = {
    "4000": "35650.75", "4100": "3000.00", "4900": "-800.25", "revenue": "37850.50",
    "5000": "14272.75", "cogs": "14272.75",
    "gross_profit": "23577.75",
    "6000": "55500.00", "6100": "9000.00", "6200": "1099.97", "6300": "2500.10",
    "operating_expenses": "68100.07",
    "operating_income": "-44522.32",
    "7000": "42.18", "other_income": "42.18",
    "net_income": "-44480.14",
}
ALL_TIME = {  # Q1 plus December's 5,000.00 and April's 9,100.00 product sales
    "4000": "49750.75", "4100": "3000.00", "4900": "-800.25", "revenue": "51950.50",
    "5000": "14272.75", "cogs": "14272.75",
    "gross_profit": "37677.75",
    "6000": "55500.00", "6100": "9000.00", "6200": "1099.97", "6300": "2500.10",
    "operating_expenses": "68100.07",
    "operating_income": "-30422.32",
    "7000": "42.18", "other_income": "42.18",
    "net_income": "-30380.14",
}


@pytest.mark.parametrize(
    "start, end, expected",
    [
        ("2026-01-01", "2026-01-31", JANUARY),
        ("2026-02-01", "2026-02-28", FEBRUARY),
        ("2026-03-01", "2026-03-31", MARCH),
        ("2026-01-01", "2026-03-31", Q1),
        ("2025-01-01", "2026-12-31", ALL_TIME),
    ],
)
def test_full_statement_matches_hand_calculation(start, end, expected):
    # Exact dict equality also proves: every P&L account is listed, no balance-sheet
    # account is, and every amount has exactly two decimal places.
    assert flatten(statement(start, end)) == expected


def test_amounts_are_decimals():
    # Decimal("0.00") == 0 is True, so equality alone would not catch an int sneaking in.
    result = statement("2026-02-01", "2026-02-28")
    numbers = [a.amount for s in result.sections for a in s.accounts]
    numbers += [s.total for s in result.sections]
    numbers += [result.gross_profit, result.operating_income, result.net_income]
    assert all(type(n) is Decimal for n in numbers)


# --- One test per trap -----------------------------------------------------------------

def test_void_entry_is_excluded():
    # JE-009 is February sales entered twice and voided.
    assert amount(statement("2026-02-01", "2026-02-28"), "4000") == Decimal("8200.00")


def test_draft_entry_is_excluded():
    # JE-019 is a 5,000.00 bonus accrual pending approval.
    assert amount(statement("2026-03-01", "2026-03-31"), "6000") == Decimal("18500.00")


def test_start_date_is_inclusive():
    # JE-007 rent is dated 2026-01-01.
    assert amount(statement("2026-01-01", "2026-01-01"), "6100") == Decimal("9000.00")


def test_end_date_is_inclusive():
    # JE-021, JE-022, JE-023 are dated 2026-03-31: 1,000.00 - 18,500.00 + 42.18.
    assert statement("2026-03-31", "2026-03-31").net_income == Decimal("-17457.82")


def test_entries_outside_the_range_are_excluded():
    assert amount(statement("2025-12-01", "2025-12-31"), "4000") == Decimal("5000.00")
    assert amount(statement("2026-04-01", "2026-04-30"), "4000") == Decimal("9100.00")


def test_contra_revenue_reduces_revenue():
    result = statement("2026-01-01", "2026-03-31")
    assert amount(result, "4900") == Decimal("-800.25")
    assert result.section("revenue").total == Decimal("37850.50")


def test_credit_to_an_expense_reduces_it():
    # JE-018 1,199.97 of software, JE-020 a 100.00 vendor credit.
    assert amount(statement("2026-03-01", "2026-03-31"), "6200") == Decimal("1099.97")


def test_inactive_account_is_still_reported():
    assert amount(statement("2026-01-01", "2026-01-31"), "6300") == Decimal("2500.10")


def test_balance_sheet_only_entries_do_not_touch_revenue():
    # JE-004 bills 12,000.00 to Deferred Revenue; only 1,000.00 is earned in January.
    assert amount(statement("2026-01-01", "2026-01-31"), "4100") == Decimal("1000.00")


def test_zero_activity_account_is_listed_as_exact_zero():
    rent = amount(statement("2026-02-01", "2026-02-28"), "6100")
    assert type(rent) is Decimal and str(rent) == "0.00"


def test_range_with_no_entries_is_all_zeros():
    result = statement("2025-06-01", "2025-06-30")
    assert set(flatten(result).values()) == {"0.00"}


def test_entry_order_in_the_file_does_not_matter():
    entries = list(LEDGER.entries)
    random.Random(0).shuffle(entries)
    shuffled = dataclasses.replace(LEDGER, entries=tuple(entries))
    assert statement("2025-01-01", "2026-12-31", shuffled) == statement("2025-01-01", "2026-12-31")


# --- Checks that must hold for every range ---------------------------------------------

def raw_net_income(start, end):
    """Independent of the app: sum credit - debit over P&L lines, straight from the JSON."""
    total = Decimal("0.00")
    for raw_entry in RAW["journal_entries"]:
        if raw_entry["status"] == "posted" and start.isoformat() <= raw_entry["date"] <= end.isoformat():
            for raw_line in raw_entry["lines"]:
                if raw_line["account"] in PNL_ACCOUNTS:
                    total += Decimal(raw_line["credit"]) - Decimal(raw_line["debit"])
    return total


@pytest.mark.parametrize("start, end", RANGES)
def test_net_income_matches_raw_lines(start, end):
    assert compute_income_statement(LEDGER, start, end).net_income == raw_net_income(start, end)


@pytest.mark.parametrize("start, end", RANGES)
def test_parts_add_up(start, end):
    result = compute_income_statement(LEDGER, start, end)
    for section in result.sections:
        assert sum((a.amount for a in section.accounts), Decimal("0")) == section.total


@pytest.mark.parametrize("start, end", RANGES)
def test_splitting_a_range_adds_up(start, end):
    whole = flatten(compute_income_statement(LEDGER, start, end))
    for split in LEDGER_DATES:
        if start <= split < end:
            left = flatten(compute_income_statement(LEDGER, start, split))
            right = flatten(compute_income_statement(LEDGER, split + timedelta(days=1), end))
            assert {key: str(Decimal(left[key]) + Decimal(right[key])) for key in whole} == whole


@pytest.mark.parametrize("start, end", RANGES)
def test_only_profit_and_loss_accounts_are_listed(start, end):
    result = compute_income_statement(LEDGER, start, end)
    assert {a.number for s in result.sections for a in s.accounts} == PNL_ACCOUNTS


# --- Drill-down and excluded entries ---------------------------------------------------

@pytest.mark.parametrize("start, end", RANGES)
def test_entries_add_up_to_their_account(start, end):
    result = compute_income_statement(LEDGER, start, end)
    for section in result.sections:
        for account in section.accounts:
            assert sum((e.amount for e in account.entries), Decimal("0")) == account.amount


@pytest.mark.parametrize("start, end", RANGES)
def test_only_posted_in_range_entries_are_counted(start, end):
    result = compute_income_statement(LEDGER, start, end)
    raw_by_id = {e["id"]: e for e in RAW["journal_entries"]}
    for section in result.sections:
        for account in section.accounts:
            for row in account.entries:
                assert raw_by_id[row.id]["status"] == "posted"
                assert start <= row.date <= end
    for excluded in result.excluded_entries:
        assert excluded.status in ("draft", "void")
        assert start <= excluded.date <= end


def test_drill_down_lists_the_entries_behind_an_account():
    software = next(a for a in statement("2026-03-01", "2026-03-31").section("operating_expenses").accounts
                    if a.number == "6200")
    assert [(e.id, str(e.amount)) for e in software.entries] == [("JE-018", "1199.97"), ("JE-020", "-100.00")]


def test_q1_excluded_entries():
    result = statement("2026-01-01", "2026-03-31")
    assert [(e.id, e.status) for e in result.excluded_entries] == [
        ("JE-009", "void"), ("JE-019", "draft"), ("JE-025", "void")]


def test_several_lines_to_one_account_in_one_entry_become_one_row():
    ledger = ledger_with(entry("JE-1", "2026-01-05", [
        line("1100", debit="300.00"),
        line("4000", credit="100.00"),
        line("4000", credit="200.00"),
    ]))
    product = statement("2026-01-01", "2026-01-31", ledger).section("revenue").accounts[0]
    assert [(e.id, str(e.amount)) for e in product.entries] == [("JE-1", "300.00")]


def test_drill_down_is_sorted_by_date_then_id():
    ledger = ledger_with(
        entry("JE-2", "2026-01-05", [line("1100", debit="2.00"), line("4000", credit="2.00")]),
        entry("JE-3", "2026-01-01", [line("1100", debit="3.00"), line("4000", credit="3.00")]),
        entry("JE-1", "2026-01-05", [line("1100", debit="1.00"), line("4000", credit="1.00")]),
    )
    product = statement("2026-01-01", "2026-01-31", ledger).section("revenue").accounts[0]
    assert [e.id for e in product.entries] == ["JE-3", "JE-1", "JE-2"]
