# Notes

## Q1 2026 net income (2026-01-01 to 2026-03-31): **(44,480.14)**, a net loss

Calculated by hand first, then confirmed by the app. It excludes draft JE-019, a $5,000 Q1
bonus accrual pending approval. If approved, the net loss becomes (49,480.14).

## Decisions and assumptions

- **Filter:** only `posted` entries, `start <= date <= end`, both ends inclusive. Voids
  (JE-009, the duplicated February sales; JE-025) and drafts (JE-019) are listed under the
  statement as "Not included", never counted. Entries are never assumed to be in date order.
- **Sign by account type, as the README says:** revenue `credit - debit`, expense
  `debit - credit`. The section comes from `subtype`. Contra revenue (4900) is revenue-type,
  so it comes out negative and reduces revenue with no special case. The vendor credit
  (JE-020) nets Software down to 1,099.97.
- **Reported as recorded:** JE-007 expenses three months of rent ($9,000) on Jan 1, so a
  January-only statement shows $9,000 and February and March show $0. Strictly, that's a
  prepaid expense to spread at $3,000 a month; per the README we don't re-accrue it.
  Inactive 6300 is still reported (`is_active` blocks new postings, not history).
  Zero-activity accounts show 0.00.
- **Money:** strings are parsed to `Decimal` once at load, never via float. JSON amounts
  are decimal strings (`"-44480.14"`). Every money `sum()` starts at `Decimal("0.00")`,
  because `sum([])` returns the int `0`. Amounts are capped at 15 digits before the point,
  so totals stay inside `Decimal`'s 28-digit precision and are never silently rounded.
- **Bad data is never hidden.** The app refuses to start only if the data can't be trusted
  at all: missing or invalid JSON, or a broken chart of accounts (a duplicate number, an
  unknown type or subtype, or a type that doesn't fit its subtype, which would give
  contradictory signs). A readable but wrong entry (posted and unbalanced, or two posted
  entries sharing an id, which may be one entry counted twice) is included and warned. An unreadable entry (an amount like `NaN`, `1e3` or `-5.00`, an unknown account
  or status, a bad date, too few lines) is left out whole and warned. When a warning could
  change the totals, `is_complete` is false and the page shows a banner. Only posted
  entries must balance.
- **Dates:** our own validator requires exact `YYYY-MM-DD`, a real date, and
  `start <= end`; anything else gets a 422. FastAPI's and `fromisoformat`'s parsing is more
  lenient (it accepts `20260101`).
- **Shape:** one FastAPI app. `/income-statement` (JSON) and `/` (HTML) both call the pure
  `compute_income_statement`. Each account drills down to its entries. No database, because
  SQLite has no exact decimal type. Labels follow accounting convention: Net revenue,
  Operating loss / Net loss, negatives in parentheses.

## How I checked the numbers

- Hand-calculated losses for Jan (21,529.65), Feb (13,230.25), Mar (9,720.24), Q1, and all
  time (30,380.14). Tests pin every account and subtotal for each.
- For every pair of ledger dates: net income equals Σ(credit − debit) over P&L lines,
  computed by a few lines over the raw JSON that share no code with the app. Entries sum to
  accounts, accounts sum to sections, and splitting a range anywhere gives parts that add up.
- One named test per trap (void, draft, both boundaries, contra, vendor credit, inactive,
  deferred revenue, zero rows, shuffled input), plus 422s and bad-data cases.
- Broke the code on purpose, and each mistake was caught: flipped sign rule (154 tests
  failed), exclusive end date (255), counting drafts (137), contra treated as expense (109),
  dropping the `Decimal("0.00")` sum start (7).

## Where AI helped, and where I didn't trust it

AI (Claude Code) wrote most of the code and tests, from a design I worked through with it
one decision at a time. It got things wrong that I caught, or that testing caught:
- It first recommended signing by *section*, contradicting the README's type-based rule.
  I pushed back. We followed the README and made the mismatch case fatal instead.
- It first proposed crashing the app on an unbalanced entry. An accountant shouldn't lose
  every report over one entry, so it became "include and warn".
- It relied on FastAPI's default date parsing, which accepts formats the README doesn't,
  so we replaced it with an explicit validator. A second review caught that `Decimal`
  parses `"NaN"` and `"1e3"` without complaint.

## Next steps

Comparative periods side by side; a balance sheet from the same ledger; an "include drafts"
preview; reloading the ledger without a restart, or moving it into storage for edits.
