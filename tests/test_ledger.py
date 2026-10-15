"""Loading: types, bad data becoming warnings, and the few cases that stop the app."""

from datetime import date
from decimal import Decimal

import pytest

from app.ledger import LedgerError, load_ledger, load_ledger_file
from tests.support import LEDGER_PATH, RAW, entry, ledger_with, line, raw_ledger


def test_real_ledger_loads_into_typed_objects():
    ledger = load_ledger_file(LEDGER_PATH)
    assert ledger.company == "Northwind Coffee Roasters" and ledger.currency == "USD"
    assert len(ledger.accounts) == 15 and len(ledger.entries) == 25
    first = ledger.entries[0]
    assert first.date == date(2025, 12, 15)
    assert first.lines[0].debit == Decimal("5000.00") and type(first.lines[0].debit) is Decimal
    assert ledger.warnings == ()


BALANCED = [line("1100", debit="5.00"), line("4000", credit="5.00")]


# --- Fatal: the app must not start -----------------------------------------------------

def test_missing_file_is_fatal(tmp_path):
    with pytest.raises(LedgerError, match="not found"):
        load_ledger_file(tmp_path / "missing.json")


def test_invalid_json_is_fatal(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text("{not json")
    with pytest.raises(LedgerError, match="not valid JSON"):
        load_ledger_file(path)


def account(number="9000", type_="expense", subtype="operating_expense"):
    return {"number": number, "name": "Test", "type": type_, "subtype": subtype, "is_active": True}


@pytest.mark.parametrize(
    "bad_account, message",
    [
        (account(number="6000"), "defined twice"),
        (account(type_="cost"), "unknown type"),
        (account(subtype="tax"), "unknown subtype"),
        (account(type_="expense", subtype="other_income"), "does not fit"),
        (account(type_="asset", subtype="cogs"), "does not fit"),
        (account(type_="revenue", subtype="balance_sheet"), "does not fit"),
    ],
)
def test_broken_chart_of_accounts_is_fatal(bad_account, message):
    with pytest.raises(LedgerError, match=message):
        load_ledger(raw_ledger(accounts=RAW["accounts"] + [bad_account]))


# --- Included and warned ---------------------------------------------------------------

def test_unbalanced_posted_entry_is_included_and_warned():
    ledger = ledger_with(entry("JE-1", "2026-01-05", [line("6000", debit="18500.00"), line("1000", credit="1850.00")]))
    assert [e.id for e in ledger.entries] == ["JE-1"]
    [warning] = ledger.warnings
    assert warning.kind == "unbalanced" and warning.affects_completeness
    assert "does not balance" in warning.message and warning.entry_date == date(2026, 1, 5)


def test_unbalanced_draft_is_not_warned():
    ledger = ledger_with(entry("JE-1", "2026-01-05", [line("6000", debit="5.00"), line("1000", credit="1.00")],
                               status="draft"))
    assert len(ledger.entries) == 1 and ledger.warnings == ()


def test_duplicate_entry_ids_are_all_included_and_warned():
    ledger = ledger_with(entry("JE-1", "2026-01-05", BALANCED), entry("JE-1", "2026-01-06", BALANCED))
    assert len(ledger.entries) == 2
    assert [w.kind for w in ledger.warnings] == ["advisory", "advisory"]
    assert not any(w.affects_completeness for w in ledger.warnings)


def test_line_with_zero_on_both_sides_is_included_and_warned():
    ledger = ledger_with(entry("JE-1", "2026-01-05", BALANCED + [line("6000")]))
    assert len(ledger.entries) == 1
    [warning] = ledger.warnings
    assert warning.kind == "advisory" and "0.00 on both sides" in warning.message


# --- Excluded (whole entry) and warned --------------------------------------------------

@pytest.mark.parametrize("bad", ["abc", "-5.00", "+5.00", "5", "5.000", "5.0", "1e3", "NaN", "Infinity",
                                 " 5.00", "5.00 ", "", None, 5.00, 5])
def test_bad_amount_excludes_the_entry(bad):
    ledger = ledger_with(entry("JE-1", "2026-01-05", [line("1100", debit=bad), line("4000", credit="5.00")]))
    assert ledger.entries == ()
    [warning] = ledger.warnings
    assert warning.kind == "skipped" and warning.affects_completeness and "JE-1 was excluded" in warning.message


@pytest.mark.parametrize(
    "bad_entry, message",
    [
        (entry("JE-1", "2026-01-05", [line("1100", debit="5.00", credit="5.00"), line("4000", credit="5.00")]),
         "both a debit and a credit"),
        (entry("JE-1", "2026-01-05", [line("1100", debit="5.00"), line("8000", credit="5.00")]),
         "'8000' does not exist"),
        (entry("JE-1", "2026-01-05", BALANCED, status="pending"), "unknown status"),
        (entry("JE-1", "2026-02-30", BALANCED), "not a valid YYYY-MM-DD date"),
        (entry("JE-1", "2026-1-5", BALANCED), "not a valid YYYY-MM-DD date"),
        (entry("JE-1", "2026-01-05", [line("1100", debit="5.00")]), "at least two lines"),
        (entry("JE-1", "2026-01-05", []), "at least two lines"),
        ({"id": "JE-1", "status": "posted", "memo": "m", "lines": BALANCED}, "not a valid YYYY-MM-DD date"),
        ({"id": "JE-1", "date": "2026-01-05", "status": "posted", "memo": "m"}, "at least two lines"),
        ({"date": "2026-01-05", "status": "posted", "memo": "m", "lines": BALANCED}, "missing id"),
        ({"id": "JE-1", "date": "2026-01-05", "status": "posted", "lines": BALANCED}, "missing memo"),
    ],
)
def test_unreadable_entry_is_excluded_and_warned(bad_entry, message):
    ledger = ledger_with(bad_entry)
    assert ledger.entries == ()
    [warning] = ledger.warnings
    assert warning.kind == "skipped" and message in warning.message


def test_skipped_void_with_readable_date_does_not_affect_completeness():
    ledger = ledger_with(entry("JE-1", "2026-01-05", [line("1100", debit="abc"), line("4000", credit="5.00")],
                               status="void"))
    [warning] = ledger.warnings
    assert warning.kind == "skipped" and not warning.affects_completeness


def test_skipped_entry_with_unreadable_date_affects_completeness_even_if_draft():
    ledger = ledger_with(entry("JE-1", "2026-02-30", BALANCED, status="draft"))
    [warning] = ledger.warnings
    assert warning.entry_date is None and warning.affects_completeness
