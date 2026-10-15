"""Shared test helpers: the real ledger, and builders for small made-up ledgers."""

import json
from pathlib import Path

from app.ledger import load_ledger

LEDGER_PATH = Path(__file__).resolve().parent.parent / "ledger.json"
RAW = json.loads(LEDGER_PATH.read_text())


def line(account, debit="0.00", credit="0.00"):
    return {"account": account, "debit": debit, "credit": credit}


def entry(entry_id, entry_date, lines, status="posted", memo="test entry"):
    return {"id": entry_id, "date": entry_date, "status": status, "memo": memo, "lines": lines}


def raw_ledger(*entries, accounts=None):
    """A ledger dict with the real chart of accounts and only the given entries."""
    return {
        "company": "Test Co",
        "currency": "USD",
        "accounts": RAW["accounts"] if accounts is None else accounts,
        "journal_entries": list(entries),
    }


def ledger_with(*entries):
    return load_ledger(raw_ledger(*entries))
