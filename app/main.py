"""Web layer: read the dates, call compute_income_statement, return JSON or HTML."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.ledger import load_ledger_file, parse_iso_date
from app.statement import IncomeStatement, compute_income_statement

LEDGER_PATH = Path(__file__).resolve().parent.parent / "ledger.json"
DEFAULT_START = date(2026, 1, 1)
DEFAULT_END = date(2026, 3, 31)

ledger = load_ledger_file(LEDGER_PATH)  # loaded once; a broken ledger stops startup
app = FastAPI(title="Income statement")
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")


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
                "total": str(section.total),
            }
            for section in statement.sections
        ],
        "gross_profit": str(statement.gross_profit),
        "operating_income": str(statement.operating_income),
        "net_income": str(statement.net_income),
        "excluded_entries": [
            {"id": entry.id, "date": entry.date.isoformat(), "status": entry.status, "memo": entry.memo}
            for entry in statement.excluded_entries
        ],
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
    }


def format_money(amount: Decimal) -> str:
    """Accountant style: 44,480.14, with negatives in parentheses: (44,480.14)."""
    text = f"{abs(amount):,.2f}"
    return f"({text})" if amount < 0 else text


def format_long_date(value: date) -> str:
    return f"{value:%B} {value.day}, {value.year}"


templates.env.filters["money"] = format_money
templates.env.filters["long_date"] = format_long_date
