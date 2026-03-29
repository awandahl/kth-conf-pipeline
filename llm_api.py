# /home/aw/production/conf/llm_api.py
import os
import sys

BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from llm_parse import parse_with_llm  # existing LLM-based parser


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
    """Return a fully populated empty result with an optional note."""
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


def _build_conf_concat(conf_name: str, conf_place: str, conf_dates: str) -> str:
    """Pretty concatenation of name, place, dates."""
    parts = []
    if conf_name:
        parts.append(conf_name)
    if conf_place:
        parts.append(conf_place)
    if conf_dates:
        parts.append(conf_dates)
    return " — ".join(parts)


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

    # 1) Delegate to existing LLM parser (returns 4 keys)
    base = parse_with_llm(raw, show_stream=show_stream) or {}

    conf_name = str(base.get("conf_name", "") or "")
    conf_place = str(base.get("conf_place", "") or "")
    conf_dates = str(base.get("conf_dates", "") or "")
    note = str(base.get("note", "") or "")

    # 2) For now, leave start/end/code/order empty.
    #    Later, we can plug in your date/series logic here.
    conf_start_date = ""
    conf_end_date = ""
    conf_code = ""
    conf_order = ""

    # 3) Build human-friendly concat string
    conf_concat = _build_conf_concat(conf_name, conf_place, conf_dates)

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
