"""Shared validation for dates and financial inputs."""
import re
from datetime import date
from fastapi import HTTPException


def valid_date(value):
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Use a valid date in YYYY-MM-DD format")
    return value


def valid_month(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("Use a valid month in YYYY-MM format")
    valid_date(value + "-01")
    return value


def month_bounds(value):
    try:
        valid_month(value)
        year, month = map(int, value.split("-"))
        return date(year, month, 1).isoformat(), date(year + month // 12, month % 12 + 1, 1).isoformat()
    except ValueError:
        raise HTTPException(422, "Choose a valid month (YYYY-MM)")
