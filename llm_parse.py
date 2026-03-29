import json
import requests
import time
import requests
from requests.exceptions import ConnectionError, Timeout
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


def maybe_add_country_from_city(place: str):
    if not place:
        return place, False

    parts = [p.strip() for p in place.split(",") if p.strip()]
    if not parts:
        return place, False

    city = parts[0]
    key = city.lower()

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
    max_retries = 3
    delay = 5  # seconds
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,  # no streaming
                    "temperature": 0.0,
                    "num_predict": 256,
                },
                timeout=120,  # seconds
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("response", "")

            if show_stream and text:
                print(text, end="", flush=True)
                print()
                print()

            return text

        except (ConnectionError, Timeout) as e:
            last_error = e
            print(f"\n[LLM] connection error (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(delay)

    # All retries failed; let pipeline's try/except handle it
    raise last_error


def parse_with_llm(conf_string: str, show_stream: bool = True):
    """
    Ask LLM to classify the string into name/place/dates.
    Returns dict with:
      conf_name, conf_place, conf_dates (normalized text), note.
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

    instruction = """
You are cleaning conference metadata.

You will receive ONE raw conference string, for example:
"38th Annual ACM Symposium on User Interface Software and Technology, UIST 2025, Busan, Korea, September 28 - October 1, 2025"

Your task is to extract:
- conf_name
- conf_place
- conf_dates
- note

You must respond as a SINGLE JSON object:
{
  "conf_name": "...",
  "conf_place": "...",
  "conf_dates": "...",
  "note": "..."
}

==================================================
1. General principles
==================================================

- Use ONLY information present in the raw string.
- Do NOT invent or guess conference names, locations, months, or days.
- If something cannot be inferred, use an empty string for that field.
- If the string only contains a date range and no recognizable name or place:
  - conf_name: ""
  - conf_place: ""
  - conf_dates: normalized date range

The "note" field:
- Very short explanation (max 20 words).
- Summarize how you interpreted the string.

==================================================
1.1 Separating name vs place
==================================================

- In many strings, the pattern is:
  "[Conference name], [City][, Region][, Country], [dates]"
- Anything after the main conference title that looks like a city/region/country
  (e.g. "Stavanger Norway", "San Diego, United States", "Busan, Korea")
  should go to conf_place, NOT conf_name.
- Do NOT keep "City Country" at the end of conf_name if it obviously denotes location.
- Example:
  Raw: "Hydropower 15 in 83rd ICOLD Meeting, Stavanger Norway"
  Good conf_name: "Hydropower 15 in 83rd ICOLD Meeting"
  Good conf_place: "Stavanger, Norway"
  conf_dates: ""  (no explicit dates in the string)

==================================================
2. conf_name rules
==================================================

2.1 What belongs in conf_name

- Include the full conference name and series, including:
  - Ordinal numbers: "12th", "38th", etc.
  - Years that clearly belong to the event name.
  - Acronyms and acronym+year patterns that refer to the specific edition.

Examples:
- "ATTCE 2001-Automotive and Transport Technology Congress and Exhibition"
- "European Congress on Computational Methods in Applied Sciences and Engineering, ECCOMAS 2004"
- "AMIF 2002, Applied Mathematics for Industrial Flow Problems, Third International Conference"
- "International Conference on Fatigue Crack Path (FCP 2003)"
- "12th IEEE/ACM International Symposium on Networks-on-Chip, NOCS 2018"

In all these cases, the year and acronym are part of the NAME and must stay in conf_name.

- If an acronym+year clearly refers to the conference edition (e.g. "HRI 2025", "UIST 2025", "DIS 2019", "ICASSP 2008"):
  - Keep the whole pattern in conf_name, not just the acronym.

Example:
Input:
"20th Annual ACM/IEEE International Conference on Human-Robot Interaction, HRI 2025, Melbourne, Australia, ..."
Good conf_name:
"20th Annual ACM/IEEE International Conference on Human-Robot Interaction, HRI 2025"

Example:
Input:
"2020 IEEE International Conference on Communications, ICC 2020; Convention Centre Dublin, Dublin; Ireland..."
Good conf_name:
"2020 IEEE International Conference on Communications, ICC 2020"

Example:
Input:
"2019 ACM Conference on Designing Interactive Systems, DIS 2019; San Diego; United States; 23 June 2019 through 28 June 2019"
Good conf_name:
"2019 ACM Conference on Designing Interactive Systems, DIS 2019"

- If the conference name starts with an abbreviation followed by a colon:
  - Keep that abbreviation and the colon in conf_name.

Example:
Input:
"SC23: The International Conference for High Performance Computing, Networking, Storage, and Analysis, Denver, CO, USA, November 12-17 2023"
Good conf_name:
"SC23: The International Conference for High Performance Computing, Networking, Storage, and Analysis"

- If the conference name starts with a year that clearly belongs to the event:
  - Keep that year in conf_name, even if dates are also in conf_dates.
  Example: "2019 ACM Conference on X"

2.2 Acronyms in parentheses

- If an acronym appears in parentheses immediately after the full name:
  - Keep the full pattern in conf_name.

Example:
Input:
"2011 American Control Conference (ACC) on O'Farrell Street, San Francisco, CA"
Good conf_name:
"2011 American Control Conference (ACC)"

- Acronyms in parentheses with or without year (e.g. "(IEEE PIMRC)") should be kept in conf_name, not dropped.

2.3 What must NOT be in conf_name

- conf_name must NOT contain explicit date expressions:
  - Days, months, date ranges, or standalone years used only as dates.
  - Examples: "27 April 2004", "April 27-29, 2004", "2004-04-27".
- These belong only in conf_dates. If such dates appear, remove them from conf_name.

2.4 Capitalization rules for conf_name

- Preserve acronyms in uppercase EXACTLY as they appear: AIAA, IEEE, IFAC, EMAS, ATTCE, etc.
- For other words, use title-style capitalization:
  - Capitalize main words.
  - Keep small connector words lowercase: and, of, on, in, for, to, the, a, an, at, by, with
    (except when they are the first word or follow a colon).

==================================================
3. conf_place rules
==================================================

3.1 What belongs in conf_place

- City/region + country (if present).
- Normalize capitalization:
  - Use "Strasbourg, France" not "STRASBOURG, FRANCE".

3.2 Diacritics

- When obvious, correct ASCII city names to local spelling with diacritics, e.g.:
  - "Jyvaskyla" -> "Jyväskylä"
  - "Goteborg" -> "Göteborg"
  - "Malmo" -> "Malmö"
- Only add diacritics when you are confident; otherwise keep a safe ASCII form.

==================================================
4. conf_dates rules
==================================================

Always normalize conf_dates using an ISO-like format.

4.1 Full date range available

- Format:
  "YYYY-MM-DD / YYYY-MM-DD"
Example:
- Input: "APR 27-29, 2004"
- conf_dates: "2004-04-27 / 2004-04-29"

4.2 Single known day

- Format:
  "YYYY-MM-DD"

4.3 Only month and year known (no specific days)

- Format:
  "YYYY-MM / YYYY-MM"
- Do NOT invent days.

4.4 Only a year known

- If the ONLY date information in the raw string is a year (e.g. "IAVSD 2019",
  "NOCS 2018") and there is NO explicit month or day anywhere:
  - Treat this as a year-only case.
  - conf_dates MUST be: "YYYY / YYYY"
  - Example: year = 2019 -> conf_dates: "2019 / 2019"
- IMPORTANT:
  - Do NOT invent months or days.
  - NEVER use patterns like "YYYY-01-01 / YYYY-12-31" when only a year is present.

4.5 General rules

- Use 4-digit years and 2-digit months/days where they are explicitly given.
- Do NOT invent specific months or days when only a year is mentioned.
- If no date information at all is available:
  - conf_dates: ""

==================================================
5. Missing information
==================================================

- If conf_name cannot be determined: use "".
- If conf_place cannot be determined: use "".
- If conf_dates cannot be determined: use "".

If the raw string only contains a date range and no recognizable name or place:
- conf_name: ""
- conf_place: ""
- conf_dates: normalized date range as above.

==================================================
6. Output format
==================================================

Respond ONLY as a single JSON object, for example:

{
  "conf_name": "2019 ACM Conference on Designing Interactive Systems, DIS 2019",
  "conf_place": "San Diego, United States",
  "conf_dates": "2019-06-23 / 2019-06-28",
  "note": "Kept acronym+year in name; extracted city, country, and full date range."
}
"""

    prompt = instruction + f"\n\nRaw conference string:\n{conf_string}\n\nJSON:"

    text = stream_llm_json(prompt, show_stream=show_stream)

    # ---- robust JSON object extraction ----
    start = text.find("{")
    if start == -1:
        result = {
            "conf_name": conf_string,
            "conf_place": "",
            "conf_dates": "",
            "note": "fallback: could not find JSON object",
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
            "note": "fallback: could not parse JSON",
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
            "note": "fallback: JSON decode error",
        }
        _llm_cache[conf_string] = result
        return result

    # ---- normalization pipeline ----
    raw_name = str(obj.get("conf_name", "") or "")
    raw_place = obj.get("conf_place", "") or ""

    # Prefer LLM's name; fall back to RAW string for casing
    name_source = raw_name or conf_string

    name_norm = normalize_conf_name(name_source)
    name_norm = strip_proceedings_noise(name_norm)
    name_norm = ensure_keep_full_name_for_as_part_of(conf_string, name_norm)
    name_norm = maybe_add_acronym_year_from_raw(conf_string, name_norm)
    name_norm = maybe_keep_parenthesized_acronym_from_raw(conf_string, name_norm)

    # Normalize place:
    # 1) fix separators ; -> ,
    # 2) normalize capitalization
    place_source = raw_place.replace(";", ",") if raw_place else raw_place
    place_norm = normalize_place(place_source)
    place_norm = normalize_us_place(place_norm)

    # 3) use GeoNames to find country from city
    place_norm, added_country = maybe_add_country_from_city(place_norm)

    note = str(obj.get("note", "") or "")
    if added_country:
        extra = " country inferred from GeoNames"
        note = (note + extra).strip() if note else extra.strip()

    # 4) collapse very long country names
    if place_norm:
        place_norm = place_norm.replace(
        "United Kingdom of Great Britain and Northern Ireland", "UK"
    )

    note = str(obj.get("note", "") or "")
    if added_country:
        extra = " country inferred from GeoNames"
        note = (note + extra).strip() if note else extra.strip()

    result = {
        "conf_name": name_norm,
        "conf_place": place_norm,
        "conf_dates": str(obj.get("conf_dates", "") or ""),
        "note": str(obj.get("note", "") or ""),
    }
    _llm_cache[conf_string] = result
    return result
