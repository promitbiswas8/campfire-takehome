# Take-home: an income statement

## Running it

Built and tested with Python 3.14.6 on macOS. Dependencies and versions are pinned in
`requirements.txt` (FastAPI 0.143.1, Jinja2 3.1.6, uvicorn 0.54.0, pytest 9.1.1, httpx2 2.13.1).

```bash
make run     # sets up .venv on first run, then starts the app
make test    # runs all tests
```

- Page: http://127.0.0.1:8000/
- JSON: http://127.0.0.1:8000/income-statement?start=2026-01-01&end=2026-03-31

`make run PORT=8001` uses another port. Without `make`:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn app.main:app --reload
pytest
```

The backend and the frontend are one process: `/` is a server-rendered page and
`/income-statement` is the JSON API. `ledger.json` is read once at startup, so restart the
server after editing it. Design: `docs/design.md`. Decisions and checks: `NOTES.md`.

---

| | |
| --- | --- |
| Track | Full-stack, backend, product-leaning |
| Language | Any language and framework. Use what you are fastest and most careful in |
| Format | Take-home, then one 45-minute review and pairing session on your code |
| AI | **On.** Use whatever tools you normally use |
| Time | 2 hours. Please stop there |
| Starter | None. You start from an empty repository |

## What you are building

A small full-stack app that shows an **income statement** (also called a P&L, profit and
loss) for a company, for any date range.

You get a chart of accounts and a set of journal entries (the data is at the end of this
file). Build:

1. **A backend** that loads the data and serves
   `GET /income-statement?start=YYYY-MM-DD&end=YYYY-MM-DD`. Any language and framework is
   fine. A database is optional. Loading the JSON at startup is fine.
2. **A frontend** with a start date, an end date, and the statement for that range. Any
   framework is fine, including server-rendered pages.
   It should be readable by an accountant. It does not need to be pretty.
3. **Tests** for the parts you think matter most.

The statement should show these sections, each with a line per account and a subtotal:

```
Revenue
Cost of goods sold
Gross profit
Operating expenses
Operating income
Other income
Net income
```

Design the response shape yourself. We will talk about the choices you made.

## Using AI

Use AI tools as much as you want. We build an AI product and use these tools every day.
What we look at is whether the result is **correct**, and whether you can explain it.
A model will write most of an income statement for you in a few minutes. It will not tell
you whether the numbers are right. That part is up to you.

In the session after the take-home, we extend your code together **without AI**. Submit
code you understand well enough to change by hand.

## You do not need to know accounting

Here is what you need.

- **Double entry.** Every journal entry has two or more lines. Each line is a debit or a
  credit to one account. In each entry, total debits equal total credits.
- **Normal balance.** Assets and expenses increase with debits. Liabilities, equity, and
  revenue increase with credits. On an income statement, revenue is shown as a positive
  number when there is more credit than debit, and an expense is shown as a positive number
  when there is more debit than credit.
- **What goes on an income statement.** Only revenue and expense accounts. Assets,
  liabilities, and equity belong on the balance sheet. They still appear in the journal
  entries, because every sale or payment touches both kinds of account.
- **A period, not a point in time.** An income statement covers the activity between two
  dates. A balance sheet shows balances as of one date. You are building the first one.

For a one-line definition of any other term, see the
[accounting primer](ACCOUNTING_PRIMER.md).

Everything else is in the data dictionary below. If something is ambiguous, make a
decision, write it down in `NOTES.md`, and move on. That is what we would do at work.

## Data dictionary

**Accounts**

| Field | Meaning |
| --- | --- |
| `number` | Account number. Journal lines refer to accounts by this number |
| `name` | Display name |
| `type` | `asset`, `liability`, `equity`, `revenue`, or `expense` |
| `subtype` | Where the account goes on the statement. See below |
| `is_active` | Whether new entries can be posted to the account today |

| `subtype` | Section |
| --- | --- |
| `operating_revenue` | Revenue |
| `contra_revenue` | Revenue. Returns, refunds, and discounts, which reduce revenue |
| `cogs` | Cost of goods sold |
| `operating_expense` | Operating expenses |
| `other_income` | Other income |
| `balance_sheet` | Not on the income statement |

**Journal entries**

| Field | Meaning |
| --- | --- |
| `id` | Entry id |
| `date` | Accounting date of the entry. There is no time or time zone |
| `status` | `posted` is in the books. `draft` is waiting for approval. `void` was cancelled |
| `memo` | Free text |

Report the entries as they were recorded. Do not re-accrue or reclassify anything.
| `lines[].account` | Account number |
| `lines[].debit`, `lines[].credit` | Decimal strings. One of the two is `"0.00"` on each line |

## What to submit

Send us a link to a Git repository (or a zip) that contains:

1. **A `README.md`** with the commands to run the backend, the frontend, and the tests. We
   should be able to run it in a few minutes on a Mac. Include the language and tool
   versions you used.
2. **A `NOTES.md`**, one page at most, with:
   - The **net income your app shows for Q1 2026, 2026-01-01 to 2026-03-31**.
   - The decisions and assumptions you made, especially about the data.
   - How you checked that the numbers are right.
   - Where AI helped, and at least one place where it got something wrong or you did not
     trust it.
   - What you would do next with more time.
3. Your code and tests. Commit as you go. We would rather see real history than one
   squashed commit.
4. **A short video**, 5 minutes at most. See [Video walkthrough](#video-walkthrough).

If you hit the 2 hours with something unfinished, stop and write down what is left in
`NOTES.md`. A correct statement with a plain page is better than an elaborate page with
wrong numbers.

## Video walkthrough

Record up to 5 minutes of screen share and send us a link. One take is fine, and it does
not count toward the 2 hours. Cover:

- How you implemented it: a quick demo, then the code path from the dates to the numbers.
- How you work: the editor, AI tools, and other tools you used, and how you used them.

## What we look at

| | |
| --- | --- |
| Correctness | The numbers are right for any date range, not only the default one |
| Money | Amounts stay exact. No floating-point rounding errors |
| Tests | The tests would catch a real mistake in the accounting, not only a typo |
| Judgment | Assumptions about the data are noticed, decided, and written down |
| Code | Someone else could read it and change it. It is sized for 2 hours, not built for scale |
| AI | You can explain everything you submitted, including the parts a model wrote |

We do not look at styling, authentication, deployment, Docker, or how many features you
added beyond the list above.

## What happens next

One 45-minute session with two engineers, in two parts:

1. **Review, about 12 minutes.** You demo the app and walk us through the code. We ask
   about your decisions and how you checked the numbers.
2. **Pairing, about 28 minutes, AI off.** We add a feature to your code together. You
   drive.

Have the app running before the session starts. We will tell you what we are adding when
we get there. It builds on the same ledger, so a codebase that is easy to change will help
you more than extra features.

## The data

Save this as `ledger.json` in your repository.

```json
{
  "company": "Northwind Coffee Roasters",
  "currency": "USD",
  "accounts": [
    {"number": "1000", "name": "Cash", "type": "asset", "subtype": "balance_sheet", "is_active": true},
    {"number": "1100", "name": "Accounts Receivable", "type": "asset", "subtype": "balance_sheet", "is_active": true},
    {"number": "1200", "name": "Inventory", "type": "asset", "subtype": "balance_sheet", "is_active": true},
    {"number": "2000", "name": "Accounts Payable", "type": "liability", "subtype": "balance_sheet", "is_active": true},
    {"number": "2100", "name": "Deferred Revenue", "type": "liability", "subtype": "balance_sheet", "is_active": true},
    {"number": "3000", "name": "Retained Earnings", "type": "equity", "subtype": "balance_sheet", "is_active": true},
    {"number": "4000", "name": "Product Revenue", "type": "revenue", "subtype": "operating_revenue", "is_active": true},
    {"number": "4100", "name": "Subscription Revenue", "type": "revenue", "subtype": "operating_revenue", "is_active": true},
    {"number": "4900", "name": "Sales Returns & Discounts", "type": "revenue", "subtype": "contra_revenue", "is_active": true},
    {"number": "5000", "name": "Cost of Goods Sold", "type": "expense", "subtype": "cogs", "is_active": true},
    {"number": "6000", "name": "Salaries", "type": "expense", "subtype": "operating_expense", "is_active": true},
    {"number": "6100", "name": "Rent", "type": "expense", "subtype": "operating_expense", "is_active": true},
    {"number": "6200", "name": "Software", "type": "expense", "subtype": "operating_expense", "is_active": true},
    {"number": "6300", "name": "Marketing (legacy)", "type": "expense", "subtype": "operating_expense", "is_active": false},
    {"number": "7000", "name": "Interest Income", "type": "revenue", "subtype": "other_income", "is_active": true}
  ],
  "journal_entries": [
    {"id": "JE-001", "date": "2025-12-15", "status": "posted", "memo": "December product sales", "lines": [
      {"account": "1100", "debit": "5000.00", "credit": "0.00"},
      {"account": "4000", "debit": "0.00", "credit": "5000.00"}]},
    {"id": "JE-002", "date": "2026-01-05", "status": "posted", "memo": "January product sales", "lines": [
      {"account": "1100", "debit": "12450.75", "credit": "0.00"},
      {"account": "4000", "debit": "0.00", "credit": "12450.75"}]},
    {"id": "JE-003", "date": "2026-01-05", "status": "posted", "memo": "January cost of goods sold", "lines": [
      {"account": "5000", "debit": "4980.30", "credit": "0.00"},
      {"account": "1200", "debit": "0.00", "credit": "4980.30"}]},
    {"id": "JE-004", "date": "2026-01-10", "status": "posted", "memo": "Annual subscription billed to Acme Cafes", "lines": [
      {"account": "1100", "debit": "12000.00", "credit": "0.00"},
      {"account": "2100", "debit": "0.00", "credit": "12000.00"}]},
    {"id": "JE-005", "date": "2026-01-31", "status": "posted", "memo": "Recognize January subscription revenue", "lines": [
      {"account": "2100", "debit": "1000.00", "credit": "0.00"},
      {"account": "4100", "debit": "0.00", "credit": "1000.00"}]},
    {"id": "JE-006", "date": "2026-01-31", "status": "posted", "memo": "January payroll", "lines": [
      {"account": "6000", "debit": "18500.00", "credit": "0.00"},
      {"account": "1000", "debit": "0.00", "credit": "18500.00"}]},
    {"id": "JE-007", "date": "2026-01-01", "status": "posted", "memo": "January to March rent, expensed when paid", "lines": [
      {"account": "6100", "debit": "9000.00", "credit": "0.00"},
      {"account": "1000", "debit": "0.00", "credit": "9000.00"}]},
    {"id": "JE-008", "date": "2026-01-20", "status": "posted", "memo": "Coffee Expo booth", "lines": [
      {"account": "6300", "debit": "2500.10", "credit": "0.00"},
      {"account": "2000", "debit": "0.00", "credit": "2500.10"}]},
    {"id": "JE-009", "date": "2026-02-03", "status": "void", "memo": "February product sales (entered twice)", "lines": [
      {"account": "1100", "debit": "8200.00", "credit": "0.00"},
      {"account": "4000", "debit": "0.00", "credit": "8200.00"}]},
    {"id": "JE-010", "date": "2026-02-03", "status": "posted", "memo": "February product sales", "lines": [
      {"account": "1100", "debit": "8200.00", "credit": "0.00"},
      {"account": "4000", "debit": "0.00", "credit": "8200.00"}]},
    {"id": "JE-011", "date": "2026-02-03", "status": "posted", "memo": "February cost of goods sold", "lines": [
      {"account": "5000", "debit": "3280.00", "credit": "0.00"},
      {"account": "1200", "debit": "0.00", "credit": "3280.00"}]},
    {"id": "JE-012", "date": "2026-02-14", "status": "posted", "memo": "Returned order, Blue Door Cafe", "lines": [
      {"account": "4900", "debit": "650.25", "credit": "0.00"},
      {"account": "1100", "debit": "0.00", "credit": "650.25"}]},
    {"id": "JE-013", "date": "2026-02-15", "status": "posted", "memo": "Payment received for January sales", "lines": [
      {"account": "1000", "debit": "12450.75", "credit": "0.00"},
      {"account": "1100", "debit": "0.00", "credit": "12450.75"}]},
    {"id": "JE-014", "date": "2026-02-28", "status": "posted", "memo": "Recognize February subscription revenue", "lines": [
      {"account": "2100", "debit": "1000.00", "credit": "0.00"},
      {"account": "4100", "debit": "0.00", "credit": "1000.00"}]},
    {"id": "JE-015", "date": "2026-02-28", "status": "posted", "memo": "February payroll", "lines": [
      {"account": "6000", "debit": "18500.00", "credit": "0.00"},
      {"account": "1000", "debit": "0.00", "credit": "18500.00"}]},
    {"id": "JE-016", "date": "2026-03-02", "status": "posted", "memo": "March product sales, 1% volume discount", "lines": [
      {"account": "1100", "debit": "14850.00", "credit": "0.00"},
      {"account": "4900", "debit": "150.00", "credit": "0.00"},
      {"account": "4000", "debit": "0.00", "credit": "15000.00"}]},
    {"id": "JE-017", "date": "2026-03-02", "status": "posted", "memo": "March cost of goods sold", "lines": [
      {"account": "5000", "debit": "6012.45", "credit": "0.00"},
      {"account": "1200", "debit": "0.00", "credit": "6012.45"}]},
    {"id": "JE-018", "date": "2026-03-10", "status": "posted", "memo": "Software subscriptions", "lines": [
      {"account": "6200", "debit": "1199.97", "credit": "0.00"},
      {"account": "2000", "debit": "0.00", "credit": "1199.97"}]},
    {"id": "JE-019", "date": "2026-03-15", "status": "draft", "memo": "Q1 bonus accrual (pending approval)", "lines": [
      {"account": "6000", "debit": "5000.00", "credit": "0.00"},
      {"account": "2000", "debit": "0.00", "credit": "5000.00"}]},
    {"id": "JE-020", "date": "2026-03-20", "status": "posted", "memo": "Credit from software vendor for overbilling", "lines": [
      {"account": "2000", "debit": "100.00", "credit": "0.00"},
      {"account": "6200", "debit": "0.00", "credit": "100.00"}]},
    {"id": "JE-021", "date": "2026-03-31", "status": "posted", "memo": "Recognize March subscription revenue", "lines": [
      {"account": "2100", "debit": "1000.00", "credit": "0.00"},
      {"account": "4100", "debit": "0.00", "credit": "1000.00"}]},
    {"id": "JE-022", "date": "2026-03-31", "status": "posted", "memo": "March payroll", "lines": [
      {"account": "6000", "debit": "18500.00", "credit": "0.00"},
      {"account": "1000", "debit": "0.00", "credit": "18500.00"}]},
    {"id": "JE-023", "date": "2026-03-31", "status": "posted", "memo": "Interest earned, March", "lines": [
      {"account": "1000", "debit": "42.18", "credit": "0.00"},
      {"account": "7000", "debit": "0.00", "credit": "42.18"}]},
    {"id": "JE-024", "date": "2026-04-01", "status": "posted", "memo": "April product sales", "lines": [
      {"account": "1100", "debit": "9100.00", "credit": "0.00"},
      {"account": "4000", "debit": "0.00", "credit": "9100.00"}]},
    {"id": "JE-025", "date": "2026-03-18", "status": "void", "memo": "Payment received from Blue Door Cafe (check returned unsigned)", "lines": [
      {"account": "1000", "debit": "3200.00", "credit": "0.00"},
      {"account": "1100", "debit": "0.00", "credit": "3200.00"}]}
  ]
}
```
