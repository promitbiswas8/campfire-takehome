"""Compute an income statement from a ledger. Pure: no files, no web."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.ledger import Account, DataWarning, JournalEntry, Ledger, Line

ZERO = Decimal("0.00")

# (key, title, subtypes), in statement order. Subtype decides the section.
SECTIONS = [
    ("revenue", "Revenue", ["operating_revenue", "contra_revenue"]),
    ("cogs", "Cost of goods sold", ["cogs"]),
    ("operating_expenses", "Operating expenses", ["operating_expense"]),
    ("other_income", "Other income", ["other_income"]),
]


@dataclass(frozen=True)
class EntryAmount:
    id: str
    date: date
    memo: str
    amount: Decimal


@dataclass(frozen=True)
class AccountAmount:
    number: str
    name: str
    amount: Decimal
    entries: tuple[EntryAmount, ...]


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    accounts: tuple[AccountAmount, ...]
    total: Decimal


@dataclass(frozen=True)
class ExcludedEntry:
    id: str
    date: date
    status: str
    memo: str


@dataclass(frozen=True)
class IncomeStatement:
    company: str
    currency: str
    start: date
    end: date
    sections: tuple[Section, ...]
    gross_profit: Decimal
    operating_income: Decimal
    net_income: Decimal
    excluded_entries: tuple[ExcludedEntry, ...]
    warnings: tuple[DataWarning, ...]
    is_complete: bool
    has_skipped_entries: bool
    has_unbalanced_entries: bool

    def section(self, key: str) -> Section:
        return next(section for section in self.sections if section.key == key)


def signed_amount(account: Account, line: Line) -> Decimal:
    """The README's rule: revenue shows credit - debit, expense shows debit - credit."""
    if account.type == "revenue":
        return line.credit - line.debit
    return line.debit - line.credit


def entry_sort_key(entry: JournalEntry):
    return (entry.date, entry.id)


def compute_income_statement(ledger: Ledger, start: date, end: date) -> IncomeStatement:
    in_range = sorted(
        (entry for entry in ledger.entries if start <= entry.date <= end),
        key=entry_sort_key,
    )
    posted = [entry for entry in in_range if entry.status == "posted"]
    excluded = tuple(
        ExcludedEntry(entry.id, entry.date, entry.status, entry.memo)
        for entry in in_range
        if entry.status != "posted"
    )

    entries_by_account = _entries_by_account(ledger, posted)

    sections = []
    for key, title, subtypes in SECTIONS:
        accounts = tuple(
            _account_amount(account, entries_by_account.get(account.number, []))
            for account in sorted(ledger.accounts.values(), key=lambda account: account.number)
            if account.subtype in subtypes
        )
        total = sum((account.amount for account in accounts), ZERO)
        sections.append(Section(key, title, accounts, total))

    totals = {section.key: section.total for section in sections}
    gross_profit = totals["revenue"] - totals["cogs"]
    operating_income = gross_profit - totals["operating_expenses"]
    net_income = operating_income + totals["other_income"]

    warnings = tuple(
        warning
        for warning in ledger.warnings
        if warning.entry_date is None or start <= warning.entry_date <= end
    )
    return IncomeStatement(
        company=ledger.company,
        currency=ledger.currency,
        start=start,
        end=end,
        sections=tuple(sections),
        gross_profit=gross_profit,
        operating_income=operating_income,
        net_income=net_income,
        excluded_entries=excluded,
        warnings=warnings,
        is_complete=not any(warning.affects_completeness for warning in warnings),
        has_skipped_entries=any(
            warning.kind == "skipped" and warning.affects_completeness for warning in warnings
        ),
        has_unbalanced_entries=any(warning.kind == "unbalanced" for warning in warnings),
    )


def _entries_by_account(ledger: Ledger, posted: list[JournalEntry]) -> dict[str, list[EntryAmount]]:
    """For each P&L account, one row per entry: that entry's lines to the account, signed."""
    result: dict[str, list[EntryAmount]] = {}
    for entry in posted:
        per_account: dict[str, Decimal] = {}
        for line in entry.lines:
            account = ledger.accounts[line.account]
            if account.subtype == "balance_sheet":
                continue
            per_account[line.account] = per_account.get(line.account, ZERO) + signed_amount(account, line)
        for number, amount in per_account.items():
            result.setdefault(number, []).append(EntryAmount(entry.id, entry.date, entry.memo, amount))
    return result


def _account_amount(account: Account, entries: list[EntryAmount]) -> AccountAmount:
    amount = sum((entry.amount for entry in entries), ZERO)
    return AccountAmount(account.number, account.name, amount, tuple(entries))
