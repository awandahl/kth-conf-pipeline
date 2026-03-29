# /home/aw/production/conf/llm_api.py
import os
import sys
import datetime

BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from llm_parse import parse_with_llm
from regex_utils import derive_dates_from_conf_dates, extract_conf_order


SCHEMA_KEYS = [
    "conf_name",
    "conf_place",
    "conf_dates",
    "conf_start_date",
    "conf_end_date",
    "conf_code",
    "conf_order",
    "conf_concat",
    "note",
]


def _empty_result(note: str = "") -> dict:
    return {
        "conf_name": "",
        "conf_place": "",
        "conf_dates": "",
        "conf_start_date": "",
        "conf_end_date": "",
        "conf_code": "",
        "conf_order": "",
        "conf_concat": "",
        "note": note or "",
    }


def _to_iso(y, m, d):
    if y is None or m is None or d is None:
        return ""
    return f"{y:04d}-{m:02d}-{d:02d}"


MONTH_NAMES = [
    None,
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _format_human_date_range(start_iso: str, end_iso: str) -> str:
    if not start_iso and not end_iso:
        return ""

    def _parse(d):
        if not d:
            return None
        try:
            return datetime.date.fromisoformat(d)
        except Exception:
            return None

    s = _parse(start_iso)
    e = _parse(end_iso)

    if s and e:
        if s.year == e.year and s.month == e.month and s.day == e.day:
            return f"{MONTH_NAMES[s.month]} {s.day}, {s.year}"
        if s.year == e.year and s.month == e.month:
            return f"{MONTH_NAMES[s.month]} {s.day}–{e.day}, {s.year}"
        if s.year == e.year:
            return (
                f"{MONTH_NAMES[s.month]} {s.day} – "
                f"{MONTH_NAMES[e.month]} {e.day}, {s.year}"
            )
        return (
            f"{MONTH_NAMES[s.month]} {s.day}, {s.year} – "
            f"{MONTH_NAMES[e.month]} {e.day}, {e.year}"
        )

    if s:
        return f"{MONTH_NAMES[s.month]} {s.day}, {s.year}"
    if e:
        return f"{MONTH_NAMES[e.month]} {e.day}, {e.year}"

    return ""


def _build_conf_concat(conf_name: str, conf_place: str, conf_dates: str) -> str:
    parts = [p for p in [conf_name, conf_place, conf_dates] if p]
    return ", ".join(parts)

def parse_conference_string(raw: str, show_stream: bool = False) -> dict:
    """
    Public API wrapper.

    Guarantees the canonical schema:
      conf_name, conf_place, conf_dates,
      conf_start_date, conf_end_date,
      conf_code, conf_order, conf_concat, note
    """
    if raw is None:
        return _empty_result(note="no input")

    raw = str(raw).strip()
    if not raw:
        return _empty_result(note="empty input")

    base = parse_with_llm(raw, show_stream=show_stream) or {}

    conf_name = str(base.get("conf_name", "") or "").strip()
    conf_place = str(base.get("conf_place", "") or "").strip()
    conf_dates = str(base.get("conf_dates", "") or "").strip()
    note = str(base.get("note", "") or "").strip()

    b_day, b_month, b_year, e_day, e_month, e_year = derive_dates_from_conf_dates(conf_dates)
    conf_start_date = _to_iso(b_year, b_month, b_day)
    conf_end_date = _to_iso(e_year, e_month, e_day)

    extracted_order = extract_conf_order(conf_name)
    conf_order = "" if extracted_order is None else str(extracted_order)

    conf_code = ""

    human_dates = _format_human_date_range(conf_start_date, conf_end_date)
    display_dates = human_dates or conf_dates
    conf_concat = _build_conf_concat(conf_name, conf_place, display_dates)

    result = {
        "conf_name": conf_name,
        "conf_place": conf_place,
        "conf_dates": conf_dates,
        "conf_start_date": conf_start_date,
        "conf_end_date": conf_end_date,
        "conf_code": conf_code,
        "conf_order": conf_order,
        "conf_concat": conf_concat,
        "note": note,
    }

    return result
