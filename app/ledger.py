"""Load ledger.json into typed objects. Data problems become warnings, not crashes."""

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

# Which account types each subtype allows. Anything else is a broken chart of accounts.
TYPES_BY_SUBTYPE = {
    "operating_revenue": {"revenue"},
    "contra_revenue": {"revenue"},
    "other_income": {"revenue"},
    "cogs": {"expense"},
    "operating_expense": {"expense"},
    "balance_sheet": {"asset", "liability", "equity"},
}
ACCOUNT_TYPES = {"asset", "liability", "equity", "revenue", "expense"}
STATUSES = {"posted", "draft", "void"}

# [0-9] rather than \d, because \d also matches non-ASCII digits. Amounts are capped at
# 15 digits before the point so sums stay inside Decimal's 28-digit precision, exactly.
AMOUNT_PATTERN = re.compile(r"[0-9]{1,15}\.[0-9]{2}")
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

ZERO = Decimal("0.00")


class LedgerError(Exception):
    """The ledger cannot be trusted at all, so the app must not start."""


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


def parse_amount(value: object) -> Decimal | None:
    """A nonnegative amount in exact 123.45 form, or None. Never goes through float."""
    if not isinstance(value, str) or not AMOUNT_PATTERN.fullmatch(value):
        return None
    return Decimal(value)


def load_ledger_file(path: Path) -> Ledger:
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise LedgerError(f"Ledger file not found: {path}")
    except json.JSONDecodeError as error:
        raise LedgerError(f"Ledger file is not valid JSON: {error}")
    return load_ledger(data)


def load_ledger(data: dict) -> Ledger:
    if not isinstance(data, dict):
        raise LedgerError("Ledger must be a JSON object")
    for key in ("company", "currency", "accounts", "journal_entries"):
        if key not in data:
            raise LedgerError(f"Ledger is missing {key!r}")
    for key in ("accounts", "journal_entries"):
        if not isinstance(data[key], list):
            raise LedgerError(f"Ledger {key!r} must be a list")

    accounts = _load_accounts(data["accounts"])
    entries = []
    warnings = []
    for raw in data["journal_entries"]:
        entry, entry_warnings = _load_entry(raw, accounts)
        if entry is not None:
            entries.append(entry)
        warnings.extend(entry_warnings)
    warnings.extend(_duplicate_id_warnings(entries))

    return Ledger(
        company=data["company"],
        currency=data["currency"],
        accounts=accounts,
        entries=tuple(entries),
        warnings=tuple(warnings),
    )


def _load_accounts(raw_accounts: list) -> dict[str, Account]:
    accounts = {}
    for raw in raw_accounts:
        try:
            account = Account(
                number=raw["number"],
                name=raw["name"],
                type=raw["type"],
                subtype=raw["subtype"],
                is_active=raw["is_active"],
            )
        except (KeyError, TypeError):
            raise LedgerError(f"Account is missing a field: {raw!r}")
        for field in ("number", "name", "type", "subtype"):
            if not isinstance(getattr(account, field), str):
                raise LedgerError(f"Account {raw!r}: {field} must be text")
        if account.number in accounts:
            raise LedgerError(f"Account {account.number} is defined twice")
        if account.type not in ACCOUNT_TYPES:
            raise LedgerError(f"Account {account.number} has unknown type {account.type!r}")
        if account.subtype not in TYPES_BY_SUBTYPE:
            raise LedgerError(f"Account {account.number} has unknown subtype {account.subtype!r}")
        if account.type not in TYPES_BY_SUBTYPE[account.subtype]:
            raise LedgerError(
                f"Account {account.number} is {account.type}-type, "
                f"which does not fit subtype {account.subtype!r}"
            )
        accounts[account.number] = account
    return accounts


def _load_entry(raw: object, accounts: dict[str, Account]) -> tuple[JournalEntry | None, list[DataWarning]]:
    """Returns (entry, warnings). The entry is None when it could not be read."""
    if not isinstance(raw, dict):
        raw = {}
    entry_id = raw.get("id") if isinstance(raw.get("id"), str) else None
    entry_date = parse_iso_date(raw.get("date"))
    status = raw.get("status") if isinstance(raw.get("status"), str) else None
    memo = raw.get("memo")
    raw_lines = raw.get("lines")

    problems = []
    if entry_id is None:
        problems.append("missing id")
    if entry_date is None:
        problems.append(f"date {raw.get('date')!r} is not a valid YYYY-MM-DD date")
    if status not in STATUSES:
        problems.append(f"unknown status {raw.get('status')!r}")
    if not isinstance(memo, str):
        problems.append("missing memo")

    lines = []
    if not isinstance(raw_lines, list) or len(raw_lines) < 2:
        problems.append("needs at least two lines")
    else:
        for number, raw_line in enumerate(raw_lines, start=1):
            line, line_problems = _load_line(raw_line, accounts)
            problems.extend(f"line {number}: {problem}" for problem in line_problems)
            if line is not None:
                lines.append(line)

    label = entry_id or "An entry with no id"
    if problems:
        # Skipping a draft or void with a readable date changes nothing we report.
        # Skipping anything else might drop a posted entry from the statement.
        affects = status not in ("draft", "void") or entry_date is None
        message = f"{label} was excluded: " + "; ".join(problems)
        return None, [DataWarning(entry_id, entry_date, "skipped", message, affects)]

    entry = JournalEntry(entry_id, entry_date, status, memo, tuple(lines))
    warnings = []
    for number, line in enumerate(entry.lines, start=1):
        if line.debit == ZERO and line.credit == ZERO:
            message = f"{label} line {number} has 0.00 on both sides"
            warnings.append(DataWarning(entry_id, entry_date, "advisory", message, False))
    if status == "posted":
        debits = sum((line.debit for line in entry.lines), ZERO)
        credits = sum((line.credit for line in entry.lines), ZERO)
        if debits != credits:
            message = (
                f"{label} is posted but does not balance: "
                f"debits {debits}, credits {credits}. It is included as recorded."
            )
            warnings.append(DataWarning(entry_id, entry_date, "unbalanced", message, True))
    return entry, warnings


def _load_line(raw: object, accounts: dict[str, Account]) -> tuple[Line | None, list[str]]:
    if not isinstance(raw, dict):
        return None, ["is not an object"]
    problems = []
    account = raw.get("account")
    if not isinstance(account, str) or account not in accounts:
        problems.append(f"account {account!r} does not exist")
    debit = parse_amount(raw.get("debit"))
    if debit is None:
        problems.append(f"debit {raw.get('debit')!r} is not an amount like 123.45")
    credit = parse_amount(raw.get("credit"))
    if credit is None:
        problems.append(f"credit {raw.get('credit')!r} is not an amount like 123.45")
    if debit is not None and credit is not None and debit != ZERO and credit != ZERO:
        problems.append("has both a debit and a credit")
    if problems:
        return None, problems
    return Line(account, debit, credit), []


def _duplicate_id_warnings(entries: list[JournalEntry]) -> list[DataWarning]:
    counts = Counter(entry.id for entry in entries)
    return [
        DataWarning(
            entry.id,
            entry.date,
            "advisory",
            f"{entry.id} appears {counts[entry.id]} times. All posted copies are counted.",
            False,
        )
        for entry in entries
        if counts[entry.id] > 1
    ]
