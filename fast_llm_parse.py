import json
import requests
from config import MODEL, OLLAMA_URL
from regex_utils import (
    normalize_conf_name,
    normalize_place,
    strip_proceedings_noise,
    normalize_us_place,
    ensure_keep_full_name_for_as_part_of,
    maybe_add_acronym_year_from_raw,
    maybe_keep_parenthesized_acronym_from_raw,
)
from geonames_cities import load_city_country

CITY_COUNTRY = load_city_country("~/geonames/cities5000.txt")

_llm_cache = {}

# ---------------------------------------------------------------------
# Toggle: include note (LLM reasoning) or not
# ---------------------------------------------------------------------
INCLUDE_NOTE = False  # set True if you want a short "note" field back

INSTRUCTION_FAST = """
You are cleaning conference metadata.

You will receive ONE raw conference string that may contain:
- A conference name
- A location (city, region, country)
- A date or date range

Extract ONLY:
- conf_name
- conf_place
- conf_dates

Rules:
- Use only information in the raw string.
- Do not invent or guess names, locations, months, or days.
- If something cannot be inferred, use an empty string for that field.

conf_dates format:
- Always normalize to an ISO-like format.
- If a full date range is given (start and end day):
  "YYYY-MM-DD / YYYY-MM-DD"
  Example: "APR 27-29, 2004" -> "2004-04-27 / 2004-04-29"
- If only one specific day is given:
  "YYYY-MM-DD"
- If only month and year are given:
  "YYYY-MM / YYYY-MM"  (same month on both sides)
- If only a year is given and no month or day appears anywhere:
  "YYYY / YYYY"
- If there is no date information at all:
  conf_dates: ""

Return a SINGLE JSON object with exactly these keys:
{
  "conf_name": "...",
  "conf_place": "...",
  "conf_dates": "..."
}

Respond with only this JSON, no explanations or extra text.
"""

INSTRUCTION_WITH_NOTE = """
You are cleaning conference metadata.

You will receive ONE raw conference string.

Extract:
- conf_name
- conf_place
- conf_dates
- note  (short explanation, max 15 words)

Rules:
- Use only information in the raw string.
- Do not invent or guess names, locations, months, or days.
- If something cannot be inferred, use an empty string for that field.

Return a SINGLE JSON object with exactly these keys:
{
  "conf_name": "...",
  "conf_place": "...",
  "conf_dates": "...",
  "note": "..."
}

Respond with only this JSON, no explanations or extra text.
"""


def maybe_add_country_from_city(place: str):
    if not place:
        return place, False

    parts = [p.strip() for p in place.split(",") if p.strip()]
    if not parts:
        return place, False

    city = parts[0]
    key = city.lower()

    # If we already have a 2‑letter region (state/province), assume country handled
    if any(len(p) == 2 and p.isupper() for p in parts[1:]):
        return place, False

    countries = CITY_COUNTRY.get(key)
    if not countries or len(countries) != 1:
        return place, False

    country_code = next(iter(countries))
    if len(parts) == 1:
        return f"{city}, {country_code}", True
    return place, False


def stream_llm_json(prompt: str, show_stream: bool = True) -> str:
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": True,
        },
        stream=True,
    )
    resp.raise_for_status()

    full_text = []
    for line in resp.iter_lines():
        if not line:
            continue
        data = json.loads(line.decode("utf-8"))
        chunk = data.get("response", "")
        if show_stream and chunk:
            print(chunk, end="", flush=True)
        full_text.append(chunk)
        if data.get("done"):
            break

    if show_stream:
        print()
        print()
    return "".join(full_text)


def parse_with_llm(conf_string: str, show_stream: bool = True):
    """
    Ask LLM to classify the string into name/place/dates.
    Returns dict with:
      conf_name, conf_place, conf_dates, note.
    """
    if conf_string is None:
        return {
            "conf_name": "",
            "conf_place": "",
            "conf_dates": "",
            "note": "",
        }

    if conf_string in _llm_cache:
        return _llm_cache[conf_string].copy()

    instruction = INSTRUCTION_WITH_NOTE if INCLUDE_NOTE else INSTRUCTION_FAST
    prompt = instruction + f"\n\nRaw conference string:\n{conf_string}\n\nJSON:"

    text = stream_llm_json(prompt, show_stream=show_stream)

    # ---- robust JSON object extraction ----
    start = text.find("{")
    if start == -1:
        result = {
            "conf_name": conf_string,
            "conf_place": "",
            "conf_dates": "",
            "note": "fallback: could not find JSON object" if INCLUDE_NOTE else "",
        }
        _llm_cache[conf_string] = result
        return result

    depth = 0
    end = -1
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        result = {
            "conf_name": conf_string,
            "conf_place": "",
            "conf_dates": "",
            "note": "fallback: could not parse JSON" if INCLUDE_NOTE else "",
        }
        _llm_cache[conf_string] = result
        return result

    json_str = text[start : end + 1]
    try:
        obj = json.loads(json_str)
    except json.JSONDecodeError:
        result = {
            "conf_name": conf_string,
            "conf_place": "",
            "conf_dates": "",
            "note": "fallback: JSON decode error" if INCLUDE_NOTE else "",
        }
        _llm_cache[conf_string] = result
        return result

    # ---- normalization pipeline ----
    raw_name = str(obj.get("conf_name", "") or "")
    raw_place = obj.get("conf_place", "") or ""
    conf_dates = str(obj.get("conf_dates", "") or "")

    name_source = raw_name or conf_string
    name_norm = normalize_conf_name(name_source)
    name_norm = strip_proceedings_noise(name_norm)
    name_norm = ensure_keep_full_name_for_as_part_of(conf_string, name_norm)
    name_norm = maybe_add_acronym_year_from_raw(conf_string, name_norm)
    name_norm = maybe_keep_parenthesized_acronym_from_raw(conf_string, name_norm)

    place_source = raw_place.replace(";", ",") if raw_place else raw_place
    place_norm = normalize_place(place_source)
    place_norm = normalize_us_place(place_norm)
    place_norm, added_country = maybe_add_country_from_city(place_norm)

    if INCLUDE_NOTE:
        note = str(obj.get("note", "") or "")
    else:
        note = ""

    if added_country:
        extra = " country inferred from GeoNames"
        note = (note + extra).strip() if note else extra.strip()

    if place_norm:
        place_norm = place_norm.replace(
            "United Kingdom of Great Britain and Northern Ireland", "UK"
        )

    result = {
        "conf_name": name_norm,
        "conf_place": place_norm,
        "conf_dates": conf_dates,
        "note": note,
    }
    _llm_cache[conf_string] = result
    return result
