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
