# Notes

## Q1 2026 net income (2026-01-01 to 2026-03-31)

**(44,480.14)**, a net loss. Hand-calculated from `ledger.json`; to be confirmed by the app.

It excludes draft JE-019, a $5,000 Q1 bonus accrual pending approval. If approved, Q1
salaries become 60,500.00 and the net loss becomes (49,480.14).

## How the statement is computed

```
start, end
  1. FILTER  posted entries with start <= date <= end (inclusive both ends)
  2. SUM     per account: total debits and total credits, exact decimals
  3. SIGN    one display number per account (see sign convention below)
  4. GROUP   account goes in a section by its subtype
  5. TOTAL   Gross profit      = Revenue - COGS
             Operating income  = Gross profit - Operating expenses
             Net income        = Operating income + Other income
```

## Decisions

- **Language: Python.** `decimal.Decimal` from the standard library keeps money exact.
- **One FastAPI app** serves both `GET /income-statement` (JSON) and `GET /` (a
  server-rendered Jinja2 page). Both call the same computation function, so there is one
  place to get the numbers right. One process, one language, nothing to build.
- **No database.** The ledger loads from `ledger.json` once at startup. I considered SQLite
  and rejected it: it has no exact decimal type, so `"2500.10"` in a NUMERIC column is
  stored as a float and `SUM()` becomes float math. Only `ledger.py` knows where the data
  comes from, so adding storage later would not touch the computation.
- **Sign convention: by account type, as the README states.** Revenue-type accounts show
  `credit - debit`. Expense-type accounts show `debit - credit`. One formula cannot work
  for every account: `credit - debit` turns Software (debits 1,199.97, credits 100.00) into
  -1,099.97, and `debit - credit` turns Product Revenue into -35,650.75. Contra revenue
  (4900) is revenue-type, so it shows as negative and reduces Revenue: (800.25) for Q1.
  The alternative, sign by section, gives identical numbers for every account in this
  ledger. It only differs for an account whose type does not match its section (e.g. an
  expense-type account under `other_income`), which this data does not have and
  which the app refuses to load (see bad data below).
- **Zero-activity accounts are shown** at 0.00, so every range has the same layout.
- **Request validation.** One explicit validator for both the JSON and HTML routes:
  exact `YYYY-MM-DD`, a real calendar date, and `start <= end`. FastAPI's own date parsing
  is more lenient than the README's format, so we don't rely on it. The JSON route returns
  422 with a reason; the page shows the error. The page defaults to Q1 only when no dates
  are given.
- **Bad data is never hidden.** Problems become warnings on any
  statement whose range includes the entry (an entry with an unreadable date warns on
  every statement). The app refuses to start only if the data cannot be trusted at all:
  `ledger.json` is missing or not JSON, or the chart of accounts is broken (an account
  number defined twice, an unknown type or subtype, or a type that does not fit its
  subtype, e.g. an expense under `other_income`, which would give contradictory signs). Every number depends on the chart
  of accounts, so a broken chart stops the app; a broken entry is flagged and skipped.
  - *Readable but wrong* is included as recorded and warned: a posted entry that does not
    balance.
  - *Readable but suspicious* is included and warned: a duplicate entry id (JE-009 shows
    duplicates happen; the accountant decides which is real), a line with zero on both sides.
  - *Unreadable* is left out of the numbers, whole entry, and warned: bad or negative
    amount, a line with both debit and credit, unknown account, unknown status, bad or
    missing date, missing fields, fewer than two lines.
    Dropping only the bad line would unbalance the rest of the entry.
  - Only posted entries must balance. That is the accounting rule: balance is enforced
    when an entry posts, and some systems allow saving an unbalanced draft.
  - Amounts must be strings of the exact form `123.45`. `Decimal` would otherwise accept
    `"NaN"`, `"1e3"` or `"-5"` without complaint.
  - **`is_complete`** is false when the totals can't be trusted: a skipped entry that may be
    posted and in range, or an included posted entry that does not balance. The page then
    shows an "Incomplete statement" banner. Ordinary draft/void exclusions never set it.
  - The current data has none of these problems (checked with a script).
- **Entries are reported as recorded, as the README says.** JE-007 expensed three months
  of rent ($9,000) on Jan 1. Q1 is right, but a January-only statement shows $9,000 of rent
  and February and March show $0. Strictly this is a prepaid expense to spread at $3,000
  a month; we do not re-accrue it.
- **Drill-down to entries.** Each account row lists the posted entries behind its amount
  (id, date, memo, amount; several lines to one account in one entry become one row,
  sorted by date then id), so every number traces back to the journal. The statement also
  lists the draft and void entries in the range that were not counted, and why.
- **Statement labels follow accounting convention:** "Net revenue" (revenue after returns
  and discounts), "Total ..." on subtotals, "Operating loss" / "Net loss" when negative,
  negatives in parentheses, thousands separators, and the period in the heading. These are
  display-only; the JSON keeps plain signed decimal strings.
- **Amounts in JSON are decimal strings** (e.g. `"-44480.14"`), so no client parses them
  into floats. The frontend only displays; it never does math.
- **Inactive accounts are reported.** `is_active` blocks new postings, not history: JE-008
  posts to 6300 Marketing (legacy), which shows 2,500.10 for Q1.

## How I checked the numbers

- Hand calculation of Q1 and of each month: Jan (21,529.65), Feb (13,230.25),
  Mar (9,720.24), which sum to Q1. All time: (30,380.14). Cross-checked with a throwaway
  script over the raw JSON. Tests pin these full statements.
- Checks that must hold for every range between dates in the ledger: net income equals
  the sum of `credit - debit` over P&L lines (a separate few-line check on the raw JSON,
  sharing no code with the app); entries sum to accounts; accounts sum to sections; and
  splitting a range at any date gives two statements that add up to the whole.
- Negative tests: bad requests return 422; balance-sheet accounts, drafts, voids and
  out-of-range entries never appear in the numbers; clean data produces no warnings.
- Broke the code on purpose (flipped the sign rule, `<=` to `<`, counted drafts, added
  contra revenue instead of subtracting it, dropped the `Decimal("0.00")` sum start) and
  confirmed a test fails for each. *(To do once built.)*
