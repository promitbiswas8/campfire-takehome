# Income statement: design

## Goal

A small app that shows Northwind Coffee Roasters' income statement for any date range,
built from `ledger.json`. Graded first on **correct numbers** and exact money, then on
tests that catch real accounting mistakes, written-down judgment about the data, and code
that can be changed by hand in a 28-minute pairing session with AI off.

Every design choice below favors: correct, small, and easy to change by hand.

## Stack

- Python (3.14 locally; code avoids anything newer than 3.11 so reviewers' Macs work).
- FastAPI + Jinja2 for the web layer; pytest + FastAPI `TestClient` for tests.
- `python3 -m venv` + `pip install -r requirements.txt`. No database: `ledger.json` loads
  once at startup.

## Files

```
ledger.json                  data, copied from the README
app/
  ledger.py                  LOAD: JSON -> typed objects + warnings. No web.
  statement.py               COMPUTE: (ledger, start, end) -> IncomeStatement. Pure. No web.
  main.py                    WEB: GET /income-statement (JSON), GET / (HTML)
  templates/statement.html   date form + statement table
tests/
  test_statement.py          accounting tests (most tests)
  test_ledger.py             bad-data warnings and fatal cases
  test_api.py                HTTP: shapes, strings, 422s, page labels
```

## Data model (`ledger.py`)

```python
@dataclass(frozen=True)
class Account:      number: str; name: str; type: str; subtype: str; is_active: bool
@dataclass(frozen=True)
class Line:         account: str; debit: Decimal; credit: Decimal
@dataclass(frozen=True)
class JournalEntry: id: str; date: date; status: str; memo: str; lines: list[Line]
@dataclass(frozen=True)
class Ledger:       company: str; currency: str
                    accounts: dict[str, Account]     # by number
                    entries: list[JournalEntry]      # file order; never assumed sorted
                    warnings: list[Warning]          # data problems found while loading
```

- Amounts are parsed **string -> `Decimal`** once here, never via float. Dates become
  `date` objects. Lines keep debit and credit as recorded; signing belongs to the statement.
- Amount strings must match `[0-9]+\.[0-9]{2}` in full and represent finite,
  nonnegative values. Reject numeric JSON values, signs, whitespace, exponent notation,
  `NaN`, infinity, and unsupported precision rather than silently rounding.
- `is_active` is loaded but not used: it blocks new postings, not history.
- `load_ledger(data: dict)` does the work; `load_ledger_file(path)` reads the file and
  calls it. Tests build small ledgers inline as dicts.

### Bad data

| Problem | Effect |
|---|---|
| `ledger.json` missing or not JSON | **App refuses to start** |
| Chart of accounts broken: duplicate account number, unknown type or subtype, incompatible type/subtype | **App refuses to start** |
| Posted entry whose debits != credits | Included as recorded, warned; affected statements marked incomplete |
| Duplicate entry id; a line with 0.00 on both sides | Included, warned |
| Bad/negative amount, line with both debit and credit, unknown account, unknown status, bad or missing date, missing fields, fewer than two lines | **Whole entry** excluded, warned |

Allowed type/subtype combinations are revenue with `operating_revenue`, `contra_revenue`,
or `other_income`; expense with `cogs` or `operating_expense`; and asset, liability, or
equity with `balance_sheet`. Reject all other combinations at startup rather than compute
contradictory signs and subtotals.

Only posted entries must balance. A warning carries the entry id (if readable), the entry
date (if readable), a message, and `affects_completeness`. A statement shows warnings whose
entry date is in its range, plus any whose date is unreadable.

`IncomeStatement.is_complete` is false when any applicable warning affects completeness:
- A whole entry was skipped and its status is posted, unknown, or unreadable.
- An included posted entry is unbalanced.
- A data failure has an unreadable date: conservatively flag every range.

Ordinary draft/void exclusions are informational and never make a statement incomplete.
Malformed entries with a readable date and a known draft/void status may generate warnings
but do not affect completeness. Duplicate-id and zero-on-both-sides warnings remain
advisory. Here, "incomplete" also covers included unbalanced posted data: the warning must
explain that the report is unreliable even though that entry was included.

## Computation (`statement.py`)

```python
SECTIONS = [
    ("revenue",            "Revenue",            ["operating_revenue", "contra_revenue"]),
    ("cogs",               "Cost of goods sold", ["cogs"]),
    ("operating_expenses", "Operating expenses", ["operating_expense"]),
    ("other_income",       "Other income",       ["other_income"]),
]

def compute_income_statement(ledger, start, end) -> IncomeStatement
```

1. **Filter**: posted entries with `start <= date <= end`. Draft and void entries in range
   go to `excluded_entries`.
2. **Sum** each P&L account's lines, starting from `Decimal("0.00")`.
3. **Sign** by account type: revenue `credit - debit`, expense `debit - credit`. Contra
   revenue comes out negative with no special case.
4. **Group** by subtype using `SECTIONS`. Every P&L account appears, even at 0.00. Accounts
   in a section are ordered by account number.
5. **Total**: section totals; gross profit = revenue - COGS; operating income = gross
   profit - operating expenses; net income = operating income + other income.

Each account row also lists its posted, in-range entries with that entry's signed amount
(same rule as the account), so entries sum to the account amount. Aggregate multiple lines
for the same account within one entry into a single drill-down amount. Sort drill-downs
and `excluded_entries` by `(date, id)` rather than relying on file order. Duplicate ids do
not merge distinct entries; ties keep file order (Python's sort is stable). *Last
priority:* use memo and recorded line contents as tie-breakers so even duplicate ids sort
the same regardless of file order.

Only addition and subtraction; no division, so no rounding.

## API

`GET /income-statement?start=YYYY-MM-DD&end=YYYY-MM-DD`

- Use one explicit date/range validator for both JSON and HTML routes: full-match
  `[0-9]{4}-[0-9]{2}-[0-9]{2}`, parse a real calendar date, then require `start <= end`.
  Do not rely on FastAPI's default date coercion to enforce the exact format.
- Missing, malformed or impossible dates -> 422 on the JSON route. `start > end` -> 422
  with a message. `start == end` is valid. The HTML route uses Q1 defaults only when no
  range is supplied; invalid or partially supplied ranges show an error.
- Amounts are **decimal strings** (`"-44480.14"`); `Decimal -> str` happens only here.

```json
{
  "company": "Northwind Coffee Roasters", "currency": "USD",
  "start": "2026-01-01", "end": "2026-03-31",
  "sections": [
    {"key": "revenue", "title": "Revenue", "total": "37850.50", "accounts": [
      {"number": "4000", "name": "Product Revenue", "amount": "35650.75", "entries": [
        {"id": "JE-002", "date": "2026-01-05", "memo": "January product sales", "amount": "12450.75"}
      ]}
    ]}
  ],
  "gross_profit": "23577.75", "operating_income": "-44522.32", "net_income": "-44480.14",
  "excluded_entries": [{"id": "JE-009", "date": "2026-02-03", "status": "void", "memo": "..."}],
  "is_complete": true,
  "warnings": []
}
```

## Page (`GET /`)

A date form (defaults to Q1 2026) and the statement, rendered from the same
`IncomeStatement` the API uses. Display-only formatting:

- Heading: company, "Income Statement", "For the period January 1, 2026 to March 31, 2026",
  currency.
- "Net revenue" for the revenue total; "Total ..." on other section totals; "Gross profit";
  "Operating income" / "Operating loss" and "Net income" / "Net loss" by sign.
- Thousands separators; negatives in parentheses.
- Each account expands with `<details>` to show its entries. No JavaScript.
- Below the statement: "Not included: N draft, M void", with the list. Keep these expected
  exclusions separate from data failures.
- Warnings appear above the statement. When `is_complete` is false, prominently show
  "Incomplete statement: some entries could not be included" for skipped entries, or
  "Incomplete statement: included posted entries do not balance" for unbalanced entries
  (both reasons if applicable). Never present affected totals as an unqualified report.
- Invalid dates show the error message on the page instead of a statement.

## Tests

Every expected number comes from the hand calculation, never from the app's output.

**`test_statement.py`**
- Full statements pinned for Jan, Feb, Mar, Q1 and all time (net income (21,529.65),
  (13,230.25), (9,720.24), (44,480.14), (30,380.14)).
- One test per trap: void excluded, draft excluded, inclusive start and end, Dec/Apr
  excluded, contra revenue reduces revenue, expense credit nets down, inactive account
  reported, balance-sheet-only entries ignored, zero-activity account is exactly
  `Decimal("0.00")`, empty range is all zeros, shuffled entries give the same result.
- For every start/end pair of ledger dates: net income equals the sum of
  `credit - debit` over P&L lines (independent check over the raw JSON); entries sum to
  accounts; accounts sum to sections; splitting the range at any date adds up.
- Negative: no balance-sheet account in any section; drill-down never shows draft, void
  or out-of-range entries; excluded entries never include posted ones; real data gives no
  warnings. Q1 excluded entries are exactly JE-009, JE-019, JE-025.

- Repeated lines for one account within an entry produce one aggregated drill-down row;
  shuffled input preserves deterministic drill-down ordering.
- Skipped potentially relevant entries and included unbalanced posted entries make the
  report incomplete; readable dates affect only matching ranges. Unreadable dates flag
  every range. Ordinary draft/void exclusions do not affect completeness. The supplied
  ledger produces complete statements.

**`test_ledger.py`**: one small inline ledger per row of the bad-data table. Explicitly
cover fatal incompatible type/subtype combinations and rejection of non-string amounts,
`NaN`, infinity, negative amounts, and unsupported fractional precision.

**`test_api.py`**: Q1 `net_income == "-44480.14"` (a string); 422 for missing, empty,
impossible (`2026-02-30`), wrong-format (`01/31/2026`, `2026-1-5`) dates and
`start > end`; `start == end` is 200; the page shows "Net loss" and "(44,480.14)".
Check equivalent date validation on the HTML route. Empty totals serialize as `"0.00"`;
assert Decimal types in computation tests too, since `Decimal("0.00") == 0` is true.
Check `is_complete` in JSON and the prominent incomplete-report banner in HTML, including
both skipped-entry and included-unbalanced-entry explanations.

**Before submitting**: break the code on purpose (flip the sign rule, `<=` to `<`, count
drafts, add contra revenue, drop the `Decimal("0.00")` start) and confirm a test fails for each.

## Build order

1. `ledger.py` (parsing only) + `statement.py` + accounting tests.
2. `main.py`, the JSON route, the page with accountant labels, API tests.
3. Drill-down and excluded entries.
4. Bad-data warnings, fatal cases, and `is_complete`.
5. Last priority: memo/line-content tie-breakers for duplicate entry ids.

Whatever is unfinished at 2 hours goes to `NOTES.md` as next steps.

## Out of scope

Database, authentication, styling beyond readable, multiple companies, comparative
periods, re-accruing or reclassifying entries.
