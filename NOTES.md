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
  entries sharing an id, which may be one entry counted twice) is included and warned. An
  unreadable entry (an amount like `NaN`, `1e3` or `-5.00`, an unknown account or status,
  a bad date, too few lines) is left out whole and warned. When a warning could
  change the totals, `is_complete` is false and the page shows a banner. Only posted
  entries must balance.
- **Dates:** our own validator requires exact `YYYY-MM-DD`, a real date, and
  `start <= end`; anything else gets a 422. The built-in parsers are more lenient:
  `date.fromisoformat` accepts `20260101`, and FastAPI accepts a Unix timestamp.
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
- Broke the code on purpose, and each mistake was caught: flipped sign rule (155 tests
  failed), exclusive end date (255), counting drafts (137), contra treated as expense (109),
  dropping the `Decimal("0.00")` sum start (7).

## Where AI helped, and where I didn't trust it

I used two separate LLM agents throughout. A primary agent (Claude Opus 5.5) handled
design and coding, and a secondary agent reviewed, audited and tested its work. Keeping
the auditor separate guards against the classic single-agent failure: editing the tests
until they pass.

- **Design.** I worked through the design with the primary agent one decision at a time,
  and used it to answer my questions, with `ACCOUNTING_PRIMER.md` as context. I checked
  each decision against my own judgment, then had the secondary agent audit the result.
  That audit caught that Python's `Decimal` quietly accepts strings like `"NaN"` and
  `"1e3"`, which led to strict amount parsing.
- **Tests and final verification** followed the same pattern: the primary agent wrote
  them, then the secondary agent and I audited them. The final review found that an
  unquoted account number made every request fail with a 500. It was fixed with a test
  written first.
- **Pushing back.** Mostly during design, I had to push back on claims and decisions. The
  agent first recommended signing amounts by section, contradicting the README's
  type-based rule. It first proposed crashing the app on an unbalanced entry, where an
  accountant would rather see the report with a warning. It also treated two posted
  entries with the same id as harmless, when one may be a double count. To its credit, it
  generally flagged the decisions it was unsure about.

Writing the code is the straightforward part with a coding agent, given a strong test
suite and a manual review. With more time, I would review more of the code line by line
myself.

## Next steps

- **Side-by-side periods** (Jan | Feb | Mar | Q1): call the pure `compute_income_statement`
  once per period and add columns. The most likely next request.
- **Preview with drafts:** a clearly labeled "if approved" view. JE-019 would take the Q1
  loss to (49,480.14).
- **Margins and % of revenue:** the first division in the app, so it needs a rounding rule
  (round once, at display, to 0.1%).
- **Balance sheet:** same loader and signs, but cumulative to a date, with net income rolled
  into retained earnings.
- **Generated test ledgers** (`hypothesis`): run the every-range checks on random balanced
  ledgers, not only on the real one.
- **Prepaid rent:** if it should be spread at $3,000/month, that's an adjusting entry in the
  books, not report logic. The report stays "as recorded".
