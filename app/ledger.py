"""Load ledger.json into typed objects. Data problems become warnings, not crashes."""

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

# [0-9] rather than \d, because \d also matches non-ASCII digits.
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


@dataclass(frozen=True)
class Account:
    number: str
    name: str
    type: str
    subtype: str
    is_active: bool


@dataclass(frozen=True)
class Line:
    account: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class JournalEntry:
    id: str
    date: date
    status: str
    memo: str
    lines: tuple[Line, ...]


@dataclass(frozen=True)
class DataWarning:
    entry_id: str | None
    entry_date: date | None  # None when the date is unreadable: the warning applies to every range
    kind: str  # "skipped", "unbalanced" or "advisory"
    message: str
    affects_completeness: bool


@dataclass(frozen=True)
class Ledger:
    company: str
    currency: str
    accounts: dict[str, Account]
    entries: tuple[JournalEntry, ...]  # file order; never assumed sorted
    warnings: tuple[DataWarning, ...]


def parse_iso_date(value: object) -> date | None:
    """A real calendar date in exact YYYY-MM-DD form, or None."""
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:  # e.g. 2026-02-30
        return None


def load_ledger_file(path: Path) -> Ledger:
    return load_ledger(json.loads(Path(path).read_text()))


def load_ledger(data: dict) -> Ledger:
    accounts = {
        raw["number"]: Account(raw["number"], raw["name"], raw["type"], raw["subtype"], raw["is_active"])
        for raw in data["accounts"]
    }
    entries = tuple(
        JournalEntry(
            id=raw["id"],
            date=date.fromisoformat(raw["date"]),
            status=raw["status"],
            memo=raw["memo"],
            lines=tuple(
                Line(raw_line["account"], Decimal(raw_line["debit"]), Decimal(raw_line["credit"]))
                for raw_line in raw["lines"]
            ),
        )
        for raw in data["journal_entries"]
    )
    return Ledger(data["company"], data["currency"], accounts, entries, warnings=())
