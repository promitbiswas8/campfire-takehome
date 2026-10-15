# Income Statement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI app that serves a correct income statement for any date range from `ledger.json`, as JSON and as an accountant-readable HTML page.

**Architecture:** `app/ledger.py` turns the JSON into frozen dataclasses (strings → `Decimal`, strings → `date`) and collects data problems as warnings. `app/statement.py` is a pure function `(ledger, start, end) → IncomeStatement`. `app/main.py` validates dates, calls it, and returns JSON (amounts as decimal strings) or renders a Jinja2 template.

**Tech Stack:** Python 3.14.6 locally (nothing newer than 3.11 syntax), FastAPI 0.143.1, Jinja2 3.1.6, uvicorn 0.54.0, pytest 9.1.1, httpx2 2.13.1 (FastAPI's `TestClient` needs it; plain `httpx` now triggers a deprecation warning).

**Spec:** `docs/design.md`. Decisions and their reasons: `NOTES.md`.

## Global Constraints

- Money is `Decimal` parsed from strings. Never `float`, never `Decimal(float)`. Every `sum()` of money starts from `Decimal("0.00")`.
- `Decimal → str` happens only in `app/main.py` (`statement_to_json`). Display formatting (commas, parentheses) happens only in the template filters.
- `statement.py` imports nothing from FastAPI and reads no files.
- Sign rule (README): revenue-type `credit - debit`, expense-type `debit - credit`. Section comes from `subtype` via `SECTIONS`.
- Only `posted` entries with `start <= date <= end` count. Both ends inclusive.
- Dates: exact `YYYY-MM-DD` (`[0-9]{4}-[0-9]{2}-[0-9]{2}`), real calendar date, `start <= end`. Bad input → 422 on JSON route, error on the page.
- Every expected number in a test comes from the hand calculation in `NOTES.md`, never from the app's output.
- Commit after every task. Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run everything from the repo root with the venv active (`source .venv/bin/activate`).

## Review Focus

Inputs the spec implies but doesn't list, most likely to bite first. Each has a test in the owning task.

1. **Names and memos with HTML characters.** `Sales Returns & Discounts` must render as text, and a memo like `<script>` must be escaped, not executed. (Task 5, Task 6)
2. **Submitting the form with both dates cleared.** The browser sends `start=&end=`, which must show an error, not Q1 and not a crash. (Task 5)
3. **Whitespace or a time on a date** (`"2026-01-01 "`, `2026-03-31T00:00:00`) must be 422, not silently accepted. (Task 4)
4. **Extreme ranges** (`0001-01-01` to `9999-12-31`) must work and equal the all-time result. (Task 4)
5. **Editing `ledger.json` while the app runs** has no effect until restart, because the ledger loads once at startup. That's by design, so the README must say so. (Task 10)

---

### Task 1: Project setup and loading the real ledger

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `.gitignore`, `app/__init__.py`, `app/ledger.py`, `tests/__init__.py`, `tests/support.py`, `tests/test_ledger.py`

**Interfaces:**
- Produces: `Account`, `Line`, `JournalEntry`, `DataWarning`, `Ledger` dataclasses; `load_ledger(data: dict) -> Ledger`; `load_ledger_file(path: Path) -> Ledger`. Test helpers `LEDGER_PATH`, `RAW`, `line()`, `entry()`, `raw_ledger()`, `ledger_with()`.

- [ ] **Step 1: Create the environment**

`requirements.txt`:
```
fastapi==0.143.1
uvicorn==0.54.0
jinja2==3.1.6
pytest==9.1.1
httpx2==2.13.1
```

`pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
```

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
```

Run:
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
touch app/__init__.py tests/__init__.py
```
(Create the `app/` and `tests/` directories first.)

- [ ] **Step 2: Write test helpers**

`tests/support.py`:
```python
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
```

- [ ] **Step 3: Write the failing test**

`tests/test_ledger.py`:
```python
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
```

- [ ] **Step 4: Run it to verify it fails**

Run: `pytest tests/test_ledger.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.ledger'`

- [ ] **Step 5: Write the loader**

`app/ledger.py`:
```python
"""Load ledger.json into typed objects. Data problems become warnings, not crashes."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


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
```

`Decimal(raw_line["debit"])` builds from the string, so it's exact. Task 7 replaces this simple loader with a validating one.

- [ ] **Step 6: Run it to verify it passes**

Run: `pytest -v`
Expected: 1 passed

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini .gitignore app tests
git commit -m "Load the ledger into typed objects

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Compute the statement, pinned to hand calculations

**Files:**
- Create: `app/statement.py`, `tests/test_statement.py`

**Interfaces:**
- Consumes: `Ledger`, `Account`, `Line` from Task 1.
- Produces: `SECTIONS`, `signed_amount(account, line) -> Decimal`, `compute_income_statement(ledger, start: date, end: date) -> IncomeStatement`. `IncomeStatement` has `company, currency, start, end, sections: tuple[Section, ...], gross_profit, operating_income, net_income` and `.section(key) -> Section`. `Section` has `key, title, accounts: tuple[AccountAmount, ...], total`. `AccountAmount` has `number, name, amount`.

- [ ] **Step 1: Write the failing tests**

`tests/test_statement.py`:
```python
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
```

(`entry`, `ledger_with`, `line`, `timedelta`, `RANGES` are imported now and used by later tasks.)

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_statement.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'app.statement'`

- [ ] **Step 3: Write the computation**

`app/statement.py`:
```python
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
```

- [ ] **Step 4: Run them to verify they pass**

Run: `pytest -v`
Expected: all pass (19 tests: 18 here plus Task 1's)

- [ ] **Step 5: Commit**

```bash
git add app/statement.py tests/test_statement.py
git commit -m "Compute the income statement, pinned to hand-calculated months

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Checks that hold for every date range

These tests should pass right away, because they check rules the Task 2 code already follows. So the "watch it fail" step is to break the code on purpose.

**Files:**
- Modify: `tests/test_statement.py` (append)

**Interfaces:**
- Consumes: `compute_income_statement`, `LEDGER`, `RAW`, `PNL_ACCOUNTS`, `LEDGER_DATES`, `RANGES`, `flatten` from Task 2.

- [ ] **Step 1: Append the tests**

Append to `tests/test_statement.py`:
```python


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
```

`raw_net_income` compares ISO date *strings*. That's safe only because every date in the real file is exact `YYYY-MM-DD`. It deliberately shares no code with the app.

- [ ] **Step 2: Run them to verify they pass**

Run: `pytest tests/test_statement.py -q`
Expected: all pass (several hundred, mostly parametrized ranges)

- [ ] **Step 3: Prove they can fail**

In `app/statement.py`, temporarily change `entry.status == "posted"` to `entry.status != "void"`.
Run: `pytest tests/test_statement.py -q -k "raw_lines"`
Expected: FAIL, net income differs by 5,000.00 for ranges that include JE-019.
Undo the change, then run `pytest -q` and expect all to pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_statement.py
git commit -m "Check net income, totals and range splits for every date range

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: JSON endpoint with strict date validation

**Files:**
- Modify: `app/ledger.py` (add `DATE_PATTERN`, `parse_iso_date`)
- Create: `app/main.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `compute_income_statement`, `IncomeStatement` from Task 2.
- Produces: `parse_iso_date(value: object) -> date | None` in `app/ledger.py` (Task 7 reuses it for entry dates). In `app/main.py`: module globals `ledger` and `app`, `DateRangeError`, `parse_date_range(start: str | None, end: str | None) -> tuple[date, date]`, `statement_to_json(statement) -> dict`.

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:
```python
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
```

`1767225600` (a Unix timestamp) and `20260101` are the inputs FastAPI's lenient parsing or `date.fromisoformat` would accept. Our regex rejects them.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_api.py -v`
Expected: FAIL, `ImportError` / `ModuleNotFoundError` for `app.main`

- [ ] **Step 3: Add the date parser to `app/ledger.py`**

Add `import re` to the imports, and below the imports:
```python
# [0-9] rather than \d, because \d also matches non-ASCII digits.
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
```

Add after the `Ledger` class:
```python
def parse_iso_date(value: object) -> date | None:
    """A real calendar date in exact YYYY-MM-DD form, or None."""
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:  # e.g. 2026-02-30
        return None
```

- [ ] **Step 4: Write `app/main.py`**

```python
"""Web layer: read the dates, call compute_income_statement, return JSON or HTML."""

from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.ledger import load_ledger_file, parse_iso_date
from app.statement import IncomeStatement, compute_income_statement

LEDGER_PATH = Path(__file__).resolve().parent.parent / "ledger.json"

ledger = load_ledger_file(LEDGER_PATH)  # loaded once; a broken ledger stops startup
app = FastAPI(title="Income statement")


class DateRangeError(ValueError):
    pass


def parse_date_range(start: str | None, end: str | None) -> tuple[date, date]:
    """The one validator for both routes: exact YYYY-MM-DD, real dates, start <= end."""
    if start is None or end is None:
        raise DateRangeError("Both start and end are required, as YYYY-MM-DD.")
    start_date = parse_iso_date(start)
    if start_date is None:
        raise DateRangeError(f"start {start!r} is not a valid date in YYYY-MM-DD form.")
    end_date = parse_iso_date(end)
    if end_date is None:
        raise DateRangeError(f"end {end!r} is not a valid date in YYYY-MM-DD form.")
    if start_date > end_date:
        raise DateRangeError("start must be on or before end.")
    return start_date, end_date


@app.get("/income-statement")
def income_statement_json(start: str | None = None, end: str | None = None) -> dict:
    try:
        start_date, end_date = parse_date_range(start, end)
    except DateRangeError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return statement_to_json(compute_income_statement(ledger, start_date, end_date))


def statement_to_json(statement: IncomeStatement) -> dict:
    """Amounts become decimal strings here, and only here."""
    return {
        "company": statement.company,
        "currency": statement.currency,
        "start": statement.start.isoformat(),
        "end": statement.end.isoformat(),
        "sections": [
            {
                "key": section.key,
                "title": section.title,
                "accounts": [
                    {"number": account.number, "name": account.name, "amount": str(account.amount)}
                    for account in section.accounts
                ],
                "total": str(section.total),
            }
            for section in statement.sections
        ],
        "gross_profit": str(statement.gross_profit),
        "operating_income": str(statement.operating_income),
        "net_income": str(statement.net_income),
    }
```

The query parameters are typed `str`, not `date`, on purpose: we validate them ourselves instead of using FastAPI's more lenient date parsing.

- [ ] **Step 5: Run them to verify they pass**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 6: Try it by hand**

Run: `uvicorn app.main:app --reload`, open `http://127.0.0.1:8000/income-statement?start=2026-01-01&end=2026-03-31`
Expected: JSON with `"net_income": "-44480.14"`. Stop the server.

- [ ] **Step 7: Commit**

```bash
git add app/ledger.py app/main.py tests/test_api.py
git commit -m "Serve the statement as JSON with strict date validation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The HTML page with accountant labels

**Files:**
- Create: `app/templates/statement.html`
- Modify: `app/main.py` (page route, filters), `tests/test_api.py` (append)

**Interfaces:**
- Consumes: `parse_date_range`, `DateRangeError`, `ledger`, `compute_income_statement`.
- Produces: `GET /`; template filters `money` (`format_money(amount: Decimal) -> str`) and `long_date` (`format_long_date(value: date) -> str`); `DEFAULT_START`, `DEFAULT_END`.

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_api.py`:
```python


# --- The page --------------------------------------------------------------------------

def test_page_defaults_to_q1_with_accountant_labels():
    response = client.get("/")
    assert response.status_code == 200
    page = response.text
    for text in ["Northwind Coffee Roasters", "For the period January 1, 2026 to March 31, 2026",
                 "Net revenue", "37,850.50", "(800.25)", "Total cost of goods sold", "Gross profit",
                 "Total operating expenses", "Operating loss", "(44,522.32)", "Net loss", "(44,480.14)"]:
        assert text in page, text


def test_page_says_income_when_positive():
    page = client.get("/", params={"start": "2026-04-01", "end": "2026-04-30"}).text
    assert "Net income" in page and "Operating income" in page and "9,100.00" in page


def test_page_escapes_html_in_names():
    assert "Sales Returns &amp; Discounts" in client.get("/").text


@pytest.mark.parametrize("params", [{"start": "2026-02-30", "end": "2026-03-31"},
                                    {"start": "2026-01-01"},
                                    {"start": "", "end": ""},
                                    {"start": "2026-03-31", "end": "2026-01-01"}])
def test_page_shows_date_errors_instead_of_a_statement(params):
    response = client.get("/", params=params)
    assert response.status_code == 422
    assert 'class="error"' in response.text and "Net loss" not in response.text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_api.py -q`
Expected: the 4 new tests FAIL (404 or missing text)

- [ ] **Step 3: Add the page route and filters to `app/main.py`**

Change the imports to:
```python
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
```

Below `LEDGER_PATH`, add:
```python
DEFAULT_START = date(2026, 1, 1)
DEFAULT_END = date(2026, 3, 31)
```

Below `app = FastAPI(...)`, add:
```python
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
```

After `income_statement_json`, add:
```python
@app.get("/", response_class=HTMLResponse)
def income_statement_page(request: Request, start: str | None = None, end: str | None = None):
    context = {"start": start or "", "end": end or "", "statement": None, "error": None}
    status_code = 200
    try:
        if start is None and end is None:
            start_date, end_date = DEFAULT_START, DEFAULT_END
        else:
            start_date, end_date = parse_date_range(start, end)
        context["start"], context["end"] = start_date.isoformat(), end_date.isoformat()
        context["statement"] = compute_income_statement(ledger, start_date, end_date)
    except DateRangeError as error:
        context["error"] = str(error)
        status_code = 422
    return templates.TemplateResponse(request, "statement.html", context, status_code=status_code)
```

At the end of the file, add:
```python
def format_money(amount: Decimal) -> str:
    """Accountant style: 44,480.14, with negatives in parentheses: (44,480.14)."""
    text = f"{abs(amount):,.2f}"
    return f"({text})" if amount < 0 else text


def format_long_date(value: date) -> str:
    return f"{value:%B} {value.day}, {value.year}"


templates.env.filters["money"] = format_money
templates.env.filters["long_date"] = format_long_date
```

Q1 is the default only when *neither* date is given. Clearing both inputs in the form sends `start=&end=`, which is an error, not Q1.

- [ ] **Step 4: Write the template**

`app/templates/statement.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Income statement</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 46rem; margin: 2rem auto; padding: 0 1rem; }
    table { width: 100%; border-collapse: collapse; }
    td { padding: 0.2rem 0.4rem; vertical-align: top; }
    td.amount { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
    tr.heading td { font-weight: bold; padding-top: 1rem; }
    tr.account td:first-child { padding-left: 1.5rem; }
    tr.total td { font-weight: bold; border-top: 1px solid #999; }
    tr.result td { font-weight: bold; border-top: 1px solid #333; }
    tr.net td { border-bottom: 3px double #333; }
    .entries { font-size: 0.85rem; color: #444; }
    .error, .warning { padding: 0.5rem 1rem; margin: 1rem 0; border: 1px solid; }
    .error, .incomplete { background: #fde8e8; border-color: #c00; }
    .warning { background: #fff6dd; border-color: #c90; }
  </style>
</head>
<body>
  <form method="get" action="/">
    <label>Start <input type="date" name="start" value="{{ start }}"></label>
    <label>End <input type="date" name="end" value="{{ end }}"></label>
    <button type="submit">Show</button>
  </form>

  {% if error %}
    <p class="error">{{ error }}</p>
  {% endif %}

  {% if statement %}
    <h1>{{ statement.company }}</h1>
    <h2>Income Statement</h2>
    <p>For the period {{ statement.start | long_date }} to {{ statement.end | long_date }}<br>({{ statement.currency }})</p>

    <table>
      {% for section in statement.sections %}
        <tr class="heading"><td colspan="2">{{ section.title }}</td></tr>
        {% for account in section.accounts %}
          <tr class="account">
            <td>{{ account.number }} {{ account.name }}</td>
            <td class="amount">{{ account.amount | money }}</td>
          </tr>
        {% endfor %}
        <tr class="total">
          <td>{% if section.key == "revenue" %}Net revenue{% else %}Total {{ section.title | lower }}{% endif %}</td>
          <td class="amount">{{ section.total | money }}</td>
        </tr>
        {% if section.key == "cogs" %}
          <tr class="result"><td>Gross profit</td><td class="amount">{{ statement.gross_profit | money }}</td></tr>
        {% elif section.key == "operating_expenses" %}
          <tr class="result"><td>{% if statement.operating_income < 0 %}Operating loss{% else %}Operating income{% endif %}</td><td class="amount">{{ statement.operating_income | money }}</td></tr>
        {% endif %}
      {% endfor %}
      <tr class="result net"><td>{% if statement.net_income < 0 %}Net loss{% else %}Net income{% endif %}</td><td class="amount">{{ statement.net_income | money }}</td></tr>
    </table>
  {% endif %}
</body>
</html>
```

`Jinja2Templates` escapes HTML automatically in `.html` templates, which is why `&` becomes `&amp;`.

- [ ] **Step 5: Run them to verify they pass**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 6: Look at it**

Run: `uvicorn app.main:app --reload`, open `http://127.0.0.1:8000/`. Check that the statement reads top to bottom like the hand calculation in `NOTES.md`. Try Feb 2026, a single day, and start after end. Stop the server.

- [ ] **Step 7: Commit**

```bash
git add app/main.py app/templates tests/test_api.py
git commit -m "Render the statement as a page with accountant labels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Drill-down to entries, and excluded entries

**Files:**
- Modify: `app/statement.py` (replace whole file), `app/main.py` (`statement_to_json`), `app/templates/statement.html`, `tests/test_statement.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: Task 2's `IncomeStatement`.
- Produces: `EntryAmount(id, date, memo, amount)`; `AccountAmount.entries: tuple[EntryAmount, ...]`; `ExcludedEntry(id, date, status, memo)`; `IncomeStatement.excluded_entries: tuple[ExcludedEntry, ...]`; `entry_sort_key(entry) -> tuple`. JSON gains `accounts[].entries` and `excluded_entries`.

- [ ] **Step 1: Append the failing statement tests**

Append to `tests/test_statement.py`:
```python


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
```

- [ ] **Step 2: Append the failing API tests**

Append to `tests/test_api.py`:
```python


def test_json_drill_down_and_excluded_entries():
    body = get_json("2026-01-01", "2026-03-31").json()
    assert body["sections"][0]["accounts"][0]["entries"][0] == {
        "id": "JE-002", "date": "2026-01-05", "memo": "January product sales", "amount": "12450.75"}
    assert [e["id"] for e in body["excluded_entries"]] == ["JE-009", "JE-019", "JE-025"]


def test_page_shows_drill_down_and_excluded_entries():
    page = client.get("/").text
    assert "JE-018" in page and "Not included: 1 draft, 2 void" in page


def test_page_escapes_html_in_memos(monkeypatch):
    monkeypatch.setattr(main, "ledger", ledger_with(
        entry("JE-1", "2026-01-05", [line("1100", debit="5.00"), line("4000", credit="5.00")],
              memo="<script>alert(1)</script>")))
    page = client.get("/", params={"start": "2026-01-01", "end": "2026-01-31"}).text
    assert "&lt;script&gt;" in page and "<script>alert" not in page
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest -q`
Expected: the new tests FAIL with `AttributeError: 'AccountAmount' object has no attribute 'entries'` / missing keys

- [ ] **Step 4: Replace `app/statement.py`**

```python
"""Compute an income statement from a ledger. Pure: no files, no web."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.ledger import Account, JournalEntry, Ledger, Line

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
```

What changed from Task 2: an account's amount is now the sum of its per-entry rows rather than of raw lines. That's the same number, but now every amount can be traced to entries. Sorting `in_range` once by `(date, id)` orders both the drill-down rows and `excluded_entries`. Python's sort is stable, so ties keep file order.

- [ ] **Step 5: Extend `statement_to_json` in `app/main.py`**

Replace the `"accounts": [...]` item inside sections with:
```python
                "accounts": [
                    {
                        "number": account.number,
                        "name": account.name,
                        "amount": str(account.amount),
                        "entries": [
                            {
                                "id": entry.id,
                                "date": entry.date.isoformat(),
                                "memo": entry.memo,
                                "amount": str(entry.amount),
                            }
                            for entry in account.entries
                        ],
                    }
                    for account in section.accounts
                ],
```

After `"net_income": ...,` add:
```python
        "excluded_entries": [
            {"id": entry.id, "date": entry.date.isoformat(), "status": entry.status, "memo": entry.memo}
            for entry in statement.excluded_entries
        ],
```

- [ ] **Step 6: Extend the template**

In `app/templates/statement.html`, replace:
```html
            <td>{{ account.number }} {{ account.name }}</td>
```
with:
```html
            <td>
              {% if account.entries %}
                <details>
                  <summary>{{ account.number }} {{ account.name }}</summary>
                  <table class="entries">
                    {% for entry in account.entries %}
                      <tr><td>{{ entry.id }}</td><td>{{ entry.date }}</td><td>{{ entry.memo }}</td><td class="amount">{{ entry.amount | money }}</td></tr>
                    {% endfor %}
                  </table>
                </details>
              {% else %}
                {{ account.number }} {{ account.name }}
              {% endif %}
            </td>
```

And replace:
```html
    </table>
  {% endif %}
```
with:
```html
    </table>

    {% if statement.excluded_entries %}
      {% set drafts = statement.excluded_entries | selectattr("status", "equalto", "draft") | list %}
      {% set voids = statement.excluded_entries | selectattr("status", "equalto", "void") | list %}
      <h3>Not included: {{ drafts | length }} draft, {{ voids | length }} void</h3>
      <ul>
        {% for entry in statement.excluded_entries %}
          <li>{{ entry.id }} ({{ entry.status }}, {{ entry.date }}): {{ entry.memo }}</li>
        {% endfor %}
      </ul>
    {% endif %}
  {% endif %}
```

(Only the last `</table>` matches, the main statement table. The entries table closes with `</table>` followed by `</details>`.)

- [ ] **Step 7: Run them to verify they pass**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add app tests
git commit -m "Trace each account to its entries and list excluded entries

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Bad data becomes warnings, a broken chart stops the app

**Files:**
- Modify: `app/ledger.py` (replace whole file), `tests/test_ledger.py` (append; change one import)

**Interfaces:**
- Consumes: `parse_iso_date` from Task 4 (kept, same signature).
- Produces: `LedgerError`; `parse_amount(value: object) -> Decimal | None`; `Ledger.warnings` populated with `DataWarning(entry_id, entry_date, kind, message, affects_completeness)` where `kind` is `"skipped"`, `"unbalanced"` or `"advisory"`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_ledger.py`, change the import to:
```python
from app.ledger import LedgerError, load_ledger, load_ledger_file
```

Append:
```python

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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_ledger.py -q`
Expected: FAIL, `ImportError: cannot import name 'LedgerError'`

- [ ] **Step 3: Replace `app/ledger.py`**

```python
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

# [0-9] rather than \d, because \d also matches non-ASCII digits.
AMOUNT_PATTERN = re.compile(r"[0-9]+\.[0-9]{2}")
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
    status = raw.get("status")
    memo = raw.get("memo")
    raw_lines = raw.get("lines")

    problems = []
    if entry_id is None:
        problems.append("missing id")
    if entry_date is None:
        problems.append(f"date {raw.get('date')!r} is not a valid YYYY-MM-DD date")
    if status not in STATUSES:
        problems.append(f"unknown status {status!r}")
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
    if account not in accounts:
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
            f"{entry.id} appears {counts[entry.id]} times. All copies are included.",
            False,
        )
        for entry in entries
        if counts[entry.id] > 1
    ]
```

Why the whole entry is skipped, not just the bad line: dropping one line would unbalance the rest of the entry. Why `affects` ignores draft/void with a readable date: those would never be counted anyway, so skipping them can't change a number.

- [ ] **Step 4: Run them to verify they pass**

Run: `pytest -q`
Expected: all pass, including every earlier test (the real ledger still loads with no warnings)

- [ ] **Step 5: Commit**

```bash
git add app/ledger.py tests/test_ledger.py
git commit -m "Flag bad journal entries as warnings; stop on a broken chart of accounts

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Completeness: tell the reader when totals can't be trusted

**Files:**
- Modify: `app/statement.py`, `app/main.py` (`statement_to_json`), `app/templates/statement.html`, `tests/test_statement.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `Ledger.warnings`, `DataWarning` from Task 7.
- Produces: `IncomeStatement.warnings: tuple[DataWarning, ...]`, `.is_complete: bool`, `.has_skipped_entries: bool`, `.has_unbalanced_entries: bool`. JSON gains `is_complete` and `warnings`.

- [ ] **Step 1: Append the failing statement tests**

Append to `tests/test_statement.py`:
```python


# --- Completeness ----------------------------------------------------------------------

def test_real_ledger_is_complete_with_no_warnings():
    result = statement("2025-01-01", "2026-12-31")
    assert result.is_complete and result.warnings == ()


def test_unbalanced_posted_entry_makes_its_range_incomplete():
    ledger = ledger_with(entry("JE-1", "2026-02-10", [line("6000", debit="18500.00"), line("1000", credit="1850.00")]))
    february = statement("2026-02-01", "2026-02-28", ledger)
    assert not february.is_complete and february.has_unbalanced_entries
    assert amount(february, "6000") == Decimal("18500.00")  # included as recorded
    assert statement("2026-01-01", "2026-01-31", ledger).is_complete


def test_skipped_posted_entry_makes_its_range_incomplete():
    ledger = ledger_with(entry("JE-1", "2026-02-10", [line("6000", debit="abc"), line("1000", credit="5.00")]))
    february = statement("2026-02-01", "2026-02-28", ledger)
    assert not february.is_complete and february.has_skipped_entries
    assert statement("2026-01-01", "2026-01-31", ledger).is_complete


def test_unreadable_date_makes_every_range_incomplete():
    ledger = ledger_with(entry("JE-1", "2026-02-30", [line("6000", debit="5.00"), line("1000", credit="5.00")]))
    assert not statement("2026-01-01", "2026-01-31", ledger).is_complete
    assert not statement("2030-01-01", "2030-01-31", ledger).is_complete


def test_skipped_draft_with_readable_date_does_not_affect_completeness():
    ledger = ledger_with(entry("JE-1", "2026-02-10", [line("6000", debit="abc"), line("1000", credit="5.00")],
                               status="draft"))
    february = statement("2026-02-01", "2026-02-28", ledger)
    assert february.is_complete and len(february.warnings) == 1


def test_ordinary_drafts_and_voids_do_not_affect_completeness():
    result = statement("2026-01-01", "2026-03-31")
    assert result.excluded_entries and result.is_complete
```

- [ ] **Step 2: Append the failing API tests**

Append to `tests/test_api.py`:
```python


def test_complete_statement_has_no_banner():
    body = get_json("2026-01-01", "2026-03-31").json()
    assert body["is_complete"] is True and body["warnings"] == []
    assert "Incomplete statement" not in client.get("/").text


def test_incomplete_statement_banner(monkeypatch):
    bad = ledger_with(
        entry("JE-1", "2026-01-05", [line("6000", debit="10.00"), line("1000", credit="1.00")]),
        entry("JE-2", "2026-01-06", [line("6000", debit="abc"), line("1000", credit="1.00")]),
    )
    monkeypatch.setattr(main, "ledger", bad)
    body = get_json("2026-01-01", "2026-01-31").json()
    assert body["is_complete"] is False and len(body["warnings"]) == 2
    page = client.get("/", params={"start": "2026-01-01", "end": "2026-01-31"}).text
    assert "Incomplete statement: some entries could not be included" in page
    assert "Incomplete statement: included posted entries do not balance" in page
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest -q`
Expected: the new tests FAIL with `AttributeError: 'IncomeStatement' object has no attribute 'is_complete'` / `KeyError: 'is_complete'`

- [ ] **Step 4: Add completeness to `app/statement.py`**

Change the ledger import to:
```python
from app.ledger import Account, DataWarning, JournalEntry, Ledger, Line
```

Add these fields to the end of `IncomeStatement` (after `excluded_entries`):
```python
    warnings: tuple[DataWarning, ...]
    is_complete: bool
    has_skipped_entries: bool
    has_unbalanced_entries: bool
```

In `compute_income_statement`, just before `return IncomeStatement(`, add:
```python
    warnings = tuple(
        warning
        for warning in ledger.warnings
        if warning.entry_date is None or start <= warning.entry_date <= end
    )
```

And add to the `IncomeStatement(...)` call, after `excluded_entries=excluded,`:
```python
        warnings=warnings,
        is_complete=not any(warning.affects_completeness for warning in warnings),
        has_skipped_entries=any(
            warning.kind == "skipped" and warning.affects_completeness for warning in warnings
        ),
        has_unbalanced_entries=any(warning.kind == "unbalanced" for warning in warnings),
```

- [ ] **Step 5: Add to `statement_to_json` in `app/main.py`**

After the `"excluded_entries": [...]` item, add:
```python
        "is_complete": statement.is_complete,
        "warnings": [
            {
                "entry_id": warning.entry_id,
                "entry_date": warning.entry_date.isoformat() if warning.entry_date else None,
                "kind": warning.kind,
                "message": warning.message,
                "affects_completeness": warning.affects_completeness,
            }
            for warning in statement.warnings
        ],
```

- [ ] **Step 6: Add the banner to the template**

In `app/templates/statement.html`, replace:
```html
  {% if statement %}
    <h1>{{ statement.company }}</h1>
```
with:
```html
  {% if statement %}
    {% if not statement.is_complete %}
      <div class="warning incomplete">
        {% if statement.has_skipped_entries %}<p><strong>Incomplete statement: some entries could not be included.</strong></p>{% endif %}
        {% if statement.has_unbalanced_entries %}<p><strong>Incomplete statement: included posted entries do not balance.</strong></p>{% endif %}
      </div>
    {% endif %}
    {% if statement.warnings %}
      <div class="warning">
        <p>Data warnings:</p>
        <ul>{% for warning in statement.warnings %}<li>{{ warning.message }}</li>{% endfor %}</ul>
      </div>
    {% endif %}

    <h1>{{ statement.company }}</h1>
```

- [ ] **Step 7: Run them to verify they pass**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add app tests
git commit -m "Mark statements incomplete when bad data could change the totals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9 (last priority): Tie-breakers for duplicate entry ids

Skip this task if time is short, and list it in `NOTES.md` as a next step.

**Files:**
- Modify: `app/statement.py` (`entry_sort_key`), `tests/test_statement.py` (append)

**Interfaces:**
- Consumes/Produces: `entry_sort_key(entry) -> tuple`, same name, longer key.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_statement.py`:
```python


def test_duplicate_ids_sort_the_same_whatever_the_file_order():
    a = entry("JE-1", "2026-01-05", [line("1100", debit="1.00"), line("4000", credit="1.00")], memo="b")
    b = entry("JE-1", "2026-01-05", [line("1100", debit="2.00"), line("4000", credit="2.00")], memo="a")
    forward = statement("2026-01-01", "2026-01-31", ledger_with(a, b))
    backward = statement("2026-01-01", "2026-01-31", ledger_with(b, a))
    assert forward.section("revenue").accounts[0].entries == backward.section("revenue").accounts[0].entries
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_statement.py -q -k duplicate_ids`
Expected: FAIL. With a stable sort on `(date, id)`, file order decides.

- [ ] **Step 3: Extend the key**

In `app/statement.py`, replace `entry_sort_key` with:
```python
def entry_sort_key(entry: JournalEntry):
    # Date, then id. Memo and line contents only break ties between duplicate ids,
    # so the order never depends on the order of the file.
    lines = tuple((line.account, line.debit, line.credit) for line in entry.lines)
    return (entry.date, entry.id, entry.memo, lines)
```

- [ ] **Step 4: Run all tests**

Run: `pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/statement.py tests/test_statement.py
git commit -m "Order duplicate entry ids the same regardless of file order

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: README, NOTES, and proving the tests catch mistakes

**Files:**
- Modify: `README.md` (add a "Running it" section at the top, keeping the prompt below), `NOTES.md`

- [ ] **Step 1: Break the code on purpose, one mistake at a time**

For each change below: make it in `app/statement.py`, run `pytest -q -x`, confirm **at least one failure**, then undo it. Record the result in `NOTES.md`.

| Mistake | Change |
|---|---|
| Flip the sign rule | `return line.credit - line.debit` → `return line.debit - line.credit` |
| Exclusive end date | `start <= entry.date <= end` → `start <= entry.date < end` |
| Count drafts | `entry.status == "posted"` → `entry.status != "void"` |
| Treat contra revenue as an expense | in `signed_amount`: `if account.type == "revenue":` → `if account.subtype in ("operating_revenue", "other_income"):` |
| Drop the Decimal sum start | `sum((entry.amount for entry in entries), ZERO)` → `sum(entry.amount for entry in entries)` |

Then run `pytest -q` and expect all to pass.

- [ ] **Step 2: Add "Running it" to the top of `README.md`**

Insert directly under the `# Take-home: an income statement` title:
````markdown
## Running it

Built and tested with Python 3.14.6 on macOS. Dependencies and versions are pinned in
`requirements.txt` (FastAPI 0.143.1, Jinja2 3.1.6, uvicorn 0.54.0, pytest 9.1.1, httpx2 2.13.1).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload     # page: http://127.0.0.1:8000/
                                  # JSON: http://127.0.0.1:8000/income-statement?start=2026-01-01&end=2026-03-31
pytest                            # all tests
```

The backend and the frontend are one process: `/` is a server-rendered page and
`/income-statement` is the JSON API. `ledger.json` is read once at startup, so restart the
server after editing it. Design: `docs/design.md`. Decisions and checks: `NOTES.md`.

---
````

- [ ] **Step 3: Finish `NOTES.md` and cut it to one page**

- Replace "to be confirmed by the app" with the app's Q1 result. Run `curl -s "http://127.0.0.1:8000/income-statement?start=2026-01-01&end=2026-03-31"` with the server running and confirm `"net_income":"-44480.14"`.
- Replace the "*(To do once built.)*" note with the Step 1 results.
- Add **Where AI helped / where I didn't trust it.** At least one concrete example. Candidates from this build: FastAPI's lenient date parsing (accepts forms the README doesn't), `Decimal("NaN")` and `Decimal("1e3")` parsing without complaint, and `sum([])` returning int `0`.
- Add **Next steps**: anything not finished, Task 9 if skipped, re-accruing the prepaid rent if asked, comparative periods.
- Condense the decisions to fit one page. The full reasoning stays in `docs/design.md`.

- [ ] **Step 4: Final check**

Run: `pytest -q` → all pass. Run the server, open `/`, and click through Q1, February, a single day, and start after end.

- [ ] **Step 5: Commit**

```bash
git add README.md NOTES.md
git commit -m "Document how to run it, the checks, and next steps

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
