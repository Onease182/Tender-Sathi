"""Bikram Sambat date parsing and normalization helpers."""

from __future__ import annotations

import re
from datetime import date

import nepali_datetime

DATE_RE = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$")


def _parts(value: str) -> tuple[int, int, int]:
    match = DATE_RE.match(str(value or "").strip())
    if not match:
        raise ValueError("Use YYYY-MM-DD format.")
    return tuple(int(part) for part in match.groups())


def parse_date(value: str, calendar: str = "auto") -> tuple[date, str]:
    """Return an AD date and the canonical BS display value.

    A four-digit year between 1900 and 2100 is interpreted as AD when the
    input is explicitly AD; otherwise values in the usual BS range are BS.
    """
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Date is optional, but cannot be blank when partially filled.")
    year, month, day = _parts(raw)
    selected = calendar.lower()
    # Common AD years are 1900–2050; typical BS years are 2000–2100.
    # The UI labels BS as primary, while explicit AD controls resolve the
    # inherently ambiguous overlap for dates such as 2024/2081.
    if selected == "ad" or (selected == "auto" and year <= 2050):
        ad_date = date(year, month, day)
        bs_date = nepali_datetime.date.from_datetime_date(ad_date)
    else:
        bs = nepali_datetime.date(year, month, day)
        ad_date = bs.to_datetime_date()
        bs_date = bs
    return ad_date, bs_date.strftime("%Y-%m-%d")


def normalize_date_pair(value: str, calendar: str = "auto") -> dict[str, str]:
    ad_date, bs_value = parse_date(value, calendar)
    return {"ad": ad_date.isoformat(), "bs": bs_value}


def display_bs(value: str) -> str:
    if not value:
        return ""
    try:
        return normalize_date_pair(value, "auto")["bs"]
    except (TypeError, ValueError, OverflowError):
        return str(value)


def period_bounds(item: dict) -> tuple[date | None, date | None]:
    start = item.get("from_ad") or item.get("from")
    end = item.get("till_ad") or item.get("till")
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except (TypeError, ValueError):
        return None, None
    return start_date, end_date
