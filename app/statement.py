"""Compute an income statement from a ledger. Pure: no files, no web."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.ledger import Account, Ledger, Line

ZERO = Decimal("0.00")

# (key, title, subtypes), in statement order. Subtype decides the section.
SECTIONS = [
    ("revenue", "Revenue", ["operating_revenue", "contra_revenue"]),
    ("cogs", "Cost of goods sold", ["cogs"]),
    ("operating_expenses", "Operating expenses", ["operating_expense"]),
    ("other_income", "Other income", ["other_income"]),
]


@dataclass(frozen=True)
class AccountAmount:
    number: str
    name: str
    amount: Decimal


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    accounts: tuple[AccountAmount, ...]
    total: Decimal


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

    def section(self, key: str) -> Section:
        return next(section for section in self.sections if section.key == key)


def signed_amount(account: Account, line: Line) -> Decimal:
    """The README's rule: revenue shows credit - debit, expense shows debit - credit."""
    if account.type == "revenue":
        return line.credit - line.debit
    return line.debit - line.credit


def compute_income_statement(ledger: Ledger, start: date, end: date) -> IncomeStatement:
    posted = [entry for entry in ledger.entries if entry.status == "posted" and start <= entry.date <= end]

    amounts: dict[str, Decimal] = {}
    for entry in posted:
        for line in entry.lines:
            account = ledger.accounts[line.account]
            if account.subtype != "balance_sheet":
                amounts[line.account] = amounts.get(line.account, ZERO) + signed_amount(account, line)

    sections = []
    for key, title, subtypes in SECTIONS:
        accounts = tuple(
            AccountAmount(account.number, account.name, amounts.get(account.number, ZERO))
            for account in sorted(ledger.accounts.values(), key=lambda account: account.number)
            if account.subtype in subtypes
        )
        total = sum((account.amount for account in accounts), ZERO)
        sections.append(Section(key, title, accounts, total))

    totals = {section.key: section.total for section in sections}
    gross_profit = totals["revenue"] - totals["cogs"]
    operating_income = gross_profit - totals["operating_expenses"]
    net_income = operating_income + totals["other_income"]

    return IncomeStatement(
        company=ledger.company,
        currency=ledger.currency,
        start=start,
        end=end,
        sections=tuple(sections),
        gross_profit=gross_profit,
        operating_income=operating_income,
        net_income=net_income,
    )
