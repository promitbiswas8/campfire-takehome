"""Loading: types, bad data becoming warnings, and the few cases that stop the app."""

from datetime import date
from decimal import Decimal

import pytest

from app.ledger import load_ledger, load_ledger_file
from tests.support import LEDGER_PATH, RAW, entry, ledger_with, line, raw_ledger


def test_real_ledger_loads_into_typed_objects():
    ledger = load_ledger_file(LEDGER_PATH)
    assert ledger.company == "Northwind Coffee Roasters" and ledger.currency == "USD"
    assert len(ledger.accounts) == 15 and len(ledger.entries) == 25
    first = ledger.entries[0]
    assert first.date == date(2025, 12, 15)
    assert first.lines[0].debit == Decimal("5000.00") and type(first.lines[0].debit) is Decimal
    assert ledger.warnings == ()
