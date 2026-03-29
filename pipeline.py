#!/usr/bin/env python3
import sys
import datetime
import os

sys.path.append(os.path.dirname(__file__))

import pandas as pd

from config import MAX_ROWS, SHOW_EVERY
from db_io import connect, fetch_conferences, write_parsed_table
from regex_utils import (
    looks_like_conference_string,
    looks_like_has_date,
    derive_dates_from_conf_dates,
    extract_conf_order,
    normalize_conf_name,
)
from llm_parse import parse_with_llm


def _to_iso(y, m, d):
    if y is None or m is None or d is None:
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


MONTH_NAMES = [
    None,
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _format_human_date_range(start_iso, end_iso):
    """
    Given start/end in 'YYYY-MM-DD' or None, return a pretty range like:
    'May 2–4, 2025' or 'May 2, 2025'.
    """
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


def _empty_core_record(note=""):
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


def main():
    con = connect()
    df = fetch_conferences(con, MAX_ROWS)
    total = len(df)
    print(f"Fetched {total} conference rows for parsing")

    rows = []

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        raw = row["conference"]
        pid = int(row["pid"])
        name_seq = int(row["name_seq"])
        show_stream = (i % SHOW_EVERY == 0)

        print(f"\n=== {i}/{total} PID {pid} name_seq {name_seq} ===")
        print("RAW:", raw)

        if looks_like_conference_string(raw) and looks_like_has_date(raw):
            if show_stream:
                print("LLM output (streaming):")
            try:
                parsed = parse_with_llm(raw, show_stream=show_stream) or {}
            except Exception as e:
                print(f"LLM error for PID {pid} name_seq {name_seq}: {e}")
                parsed = {
                    "conf_name": normalize_conf_name(raw),
                    "conf_place": "",
                    "conf_dates": "",
                    "note": f"LLM error: {e}",
                }
        else:
            parsed = {
                "conf_name": normalize_conf_name(raw),
                "conf_place": "",
                "conf_dates": "",
                "note": "no date detected or skipped by heuristic",
            }

        # === 9-field core schema ============================================
        conf_name = (parsed.get("conf_name") or "").strip()
        conf_place = (parsed.get("conf_place") or "").strip()
        conf_dates = (parsed.get("conf_dates") or "").strip()
        note = (parsed.get("note") or "").strip()
        conf_code = (parsed.get("conf_code") or "").strip()

        # derive granular dates from conf_dates string
        b_day, b_month, b_year, e_day, e_month, e_year = derive_dates_from_conf_dates(conf_dates)
        conf_start_date = _to_iso(b_year, b_month, b_day) or ""
        conf_end_date = _to_iso(e_year, e_month, e_day) or ""

        conf_year_start = b_year
        conf_year_end = e_year

        # conference order (edition number) from name
        extracted_order = extract_conf_order(conf_name)
        conf_order = extracted_order

        # pretty concatenated display string
        human_dates = _format_human_date_range(conf_start_date or None, conf_end_date or None)
        display_dates = human_dates or conf_dates
        parts = [p for p in [conf_name, conf_place, display_dates] if p]
        conf_concat = ", ".join(parts)

        core = _empty_core_record(note=note)
        core.update(
            {
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
        )

        print(
            "PARSED:",
            f"name='{core['conf_name']}' | "
            f"place='{core['conf_place']}' | "
            f"dates='{core['conf_dates']}' | "
            f"start='{core['conf_start_date']}' | "
            f"end='{core['conf_end_date']}' | "
            f"code='{core['conf_code']}' | "
            f"order='{core['conf_order']}' | "
            f"concat='{core['conf_concat']}'",
        )

        if core["note"]:
            print("NOTE:", core["note"])

        # === DBLP enrichment layer ==========================================
        dblp_series_slug = None
        dblp_series_stream_iri = None
        dblp_series_name = None
        dblp_series_match_reason = "dblp lookup disabled"

        print("DBLP: lookup disabled")
        print()
        print()
        print()

        rows.append(
            {
                # identifiers
                "pid": pid,
                "name_seq": name_seq,
                "raw_conference": raw,

                # 9 core conference fields
                "conf_name": core["conf_name"],
                "conf_place": core["conf_place"],
                "conf_dates": core["conf_dates"],
                "conf_start_date": core["conf_start_date"],
                "conf_end_date": core["conf_end_date"],
                "conf_code": core["conf_code"],
                "conf_order": core["conf_order"],
                "conf_concat": core["conf_concat"],
                "note": core["note"],

                # additional derived fields
                "conf_year_start": conf_year_start,
                "conf_year_end": conf_year_end,

                # DBLP-specific enrichment
                "dblp_series_slug": dblp_series_slug,
                "dblp_series_stream_iri": dblp_series_stream_iri,
                "dblp_series_name": dblp_series_name,
                "dblp_series_match_reason": dblp_series_match_reason,
            }
        )

    out = pd.DataFrame(rows)
    print("\nSample of parsed output:")
    print(out.head(20).to_string(index=False))

    write_parsed_table(con, out, "names_conference_parsed")
    out.to_csv("names_conference_parsed_sample.csv", index=False)

    con.close()
    print("\nDone. Wrote parsed data to 'names_conference_parsed' and CSV.")


if __name__ == "__main__":
    main()
