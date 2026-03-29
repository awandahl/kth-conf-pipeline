import re

MIN_LEN_FOR_LLM = 10
MAX_LEN_FOR_LLM = 400

HAS_YEAR = re.compile(r"\b(19|20)\d{2}\b")
HAS_MONTH = re.compile(
    r"\b("
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
    r"January|February|March|April|June|July|August|September|October|November|December"
    r")\b",
    re.IGNORECASE,
)
HTML_TAG_RE = re.compile(r"<[^>]+>")
MANY_DIGITS_RE = re.compile(r"\d{6,}")

SMALL_WORDS = {
    "and", "or", "of", "on", "in", "for", "to", "the", "a", "an", "at", "by", "with",
}
ACRONYM_OVERRIDES = {"eccomas": "ECCOMAS"}

US_STATE_ABBREVS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "D.C.",
}

US_STATE_FULL_TO_ABBR = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}

# --- date range parsing for conf_dates -> granular fields -------------

ISO_RANGE_RE = re.compile(
    r"""
    ^
    (?P<start>\d{4}(?:-\d{2}(?:-\d{2})?)?)
    (?:\s*/\s*
       (?P<end>\d{4}(?:-\d{2}(?:-\d{2})?)?)
    )?
    $
    """,
    re.VERBOSE,
)


def parse_iso_like_date(s: str):
    """
    Parse 'YYYY', 'YYYY-MM' or 'YYYY-MM-DD' into (year, month, day).
    Missing parts become None.
    """
    if not s:
        return (None, None, None)
    parts = s.split("-")
    try:
        year = int(parts[0])
    except ValueError:
        return (None, None, None)
    month = int(parts[1]) if len(parts) >= 2 else None
    day = int(parts[2]) if len(parts) >= 3 else None
    return (year, month, day)


def derive_dates_from_conf_dates(conf_dates: str):
    """
    Take a conf_dates string in your existing formats, e.g.
      '2008-02-18 / 2008-02-21'
      '2019-06 / 2019-06'
      '2019 / 2019'
    and return:
      (start_day, start_month, start_year, end_day, end_month, end_year)
    where each component may be None.
    """
    if not conf_dates:
        return (None, None, None, None, None, None)

    m = ISO_RANGE_RE.match(conf_dates.strip())
    if not m:
        return (None, None, None, None, None, None)

    start_raw = m.group("start")
    end_raw = m.group("end") or start_raw

    sy, sm, sd = parse_iso_like_date(start_raw)
    ey, em, ed = parse_iso_like_date(end_raw)

    return (sd, sm, sy, ed, em, ey)


# --- abbreviation expansion -------------------------------------------

ABBREV_REPLACEMENTS = {
    r"\bint\.?\s+conf\.?\b": "International Conference",
    r"\bint\.?\s+symp\.?\b": "International Symposium",
    r"\bint\.?\s+worksh\.?\b": "International Workshop",
    r"\bint\.?\s+workshop\b": "International Workshop",
    r"\bintl\.?\s+conf\.?\b": "International Conference",
    r"\bconf\.?\b": "Conference",
    r"\bsymp\.?\b": "Symposium",
    r"\bworksh\.?\b": "Workshop",
}


def expand_abbreviations(text: str) -> str:
    if not text:
        return text
    s = str(text)
    for pat, repl in ABBREV_REPLACEMENTS.items():
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)
    return s


# Matches: 'as a part of', 'as part of', 'held as part of', etc.
AS_PART_OF_RE = re.compile(
    r"\b(?:held\s+)?as\s+(?:a\s+)?part\s+of\b",
    re.IGNORECASE,
)


def ensure_keep_full_name_for_as_part_of(raw_name: str, llm_name: str) -> str:
    """
    If the raw string contains 'as a part of', return the raw_name (normalized),
    otherwise trust the LLM's conf_name.
    """
    if not raw_name:
        return llm_name
    if AS_PART_OF_RE.search(str(raw_name)):
        return normalize_conf_name(str(raw_name))
    return llm_name


def looks_like_has_date(text: str) -> bool:
    if not text:
        return False
    t = str(text).strip()
    return bool(HAS_YEAR.search(t) or HAS_MONTH.search(t))


def looks_like_conference_string(text: str) -> bool:
    if text is None:
        return False
    t = str(text).strip()
    if len(t) < MIN_LEN_FOR_LLM or len(t) > MAX_LEN_FOR_LLM:
        return False
    if HTML_TAG_RE.search(t):
        return False
    if MANY_DIGITS_RE.search(t):
        return False
    return True


def normalize_place(place: str) -> str:
    if not place:
        return place
    p = str(place).strip()
    letters = "".join(ch for ch in p if ch.isalpha())
    if letters and letters.isupper():
        return p.lower().title()
    return p


def normalize_us_place(place: str) -> str:
    """
    Handle US states (abbrev or spelled-out) and ensure 'USA' as country.
    """
    if not place:
        return place
    p = str(place).strip()
    parts = [x.strip() for x in p.split(",")]
    if not parts:
        return p

    # Normalize 'United States...' → 'USA'
    if len(parts) >= 2:
        last = parts[-1]
        if last.lower().startswith("united states"):
            parts[-1] = "USA"
            return ", ".join(parts)

    # Spelled-out state names
    if len(parts) >= 2:
        last = parts[-1].lower()
        two_last = (parts[-2] + " " + parts[-1]).lower() if len(parts) >= 2 else None

        if last in US_STATE_FULL_TO_ABBR:
            abbr = US_STATE_FULL_TO_ABBR[last]
            city = ", ".join(parts[:-1])
            return f"{city}, {abbr}, USA"

        if two_last in US_STATE_FULL_TO_ABBR and len(parts) >= 3:
            abbr = US_STATE_FULL_TO_ABBR[two_last]
            city = ", ".join(parts[:-2])
            return f"{city}, {abbr}, USA"

    # "City, ST" → "City, ST, USA"
    if len(parts) == 2:
        city, st = parts
        if st.upper() in US_STATE_ABBREVS:
            return f"{city}, {st.upper()}, USA"

    # "City, ST, Country" with ST a US state → normalize country to USA
    if len(parts) >= 3:
        st = parts[-2]
        if st.upper() in US_STATE_ABBREVS:
            parts[-1] = "USA"
            return ", ".join(parts)

    return p


def normalize_conf_name(name: str) -> str:
    if not name:
        return name
    text = str(name).strip()

    text = expand_abbreviations(text)

    tokens = re.split(r"(\s+)", text)
    result = []
    start_of_segment = True

    for tok in tokens:
        if tok.isspace():
            result.append(tok)
            continue

        word = tok
        trailing = ""
        m = re.match(r"^([A-Za-z0-9]+)(.*)$", tok)
        if m:
            word, trailing = m.group(1), m.group(2)

        lower_word = word.lower()

        if lower_word in ACRONYM_OVERRIDES:
            new_word = ACRONYM_OVERRIDES[lower_word]
        elif word.isupper() and len(word) > 1:
            new_word = word
        else:
            if start_of_segment:
                new_word = word[:1].upper() + word[1:].lower()
            else:
                if lower_word in SMALL_WORDS:
                    new_word = lower_word
                else:
                    new_word = word[:1].upper() + word[1:].lower()

        result.append(new_word + trailing)
        start_of_segment = ":" in tok

    return "".join(result)


# --- conference order extraction (series number) ----------------------

ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty-first": 21, "twenty-second": 22,
    "twenty-third": 23, "twenty-fourth": 24, "twenty-fifth": 25,
    "twenty-sixth": 26, "twenty-seventh": 27, "twenty-eighth": 28,
    "twenty-ninth": 29, "thirtieth": 30, "thirty-first": 31, "thirty-second": 32,
    "thirty-third": 33, "thirty-fourth": 34, "thirty-fifth": 35,
    "thirty-sixth": 36, "thirty-seventh": 37, "thirty-eighth": 38,
    "thirty-ninth": 39, "fortieth": 40, "forty-first": 41, "forty-second": 42,
    "forty-third": 43, "forty-fourth": 44, "forty-fifth": 45,
    "forty-sixth": 46, "forty-seventh": 47, "forty-eighth": 48,
    "forty-ninth": 49, "fiftieth": 50, "fifty-first": 51, "fifty-second": 52,
    "fifty-third": 53, "fifty-fourth": 54, "fifty-fifth": 55,
    "fifty-sixth": 56, "fifty-seventh": 57, "fifty-eighth": 58,
    "fifty-ninth": 59, "sixtieth": 60, "sixty-first": 61, "sixty-second": 62,
    "sixty-third": 63, "sixty-fourth": 64, "sixty-fifth": 65,
    "sixty-sixth": 66, "sixty-seventh": 67, "sixty-eighth": 68,
    "sixty-ninth": 69, "seventieth": 70, "seventy-first": 71,
    "seventy-second": 72, "seventy-third": 73, "seventy-fourth": 74,
    "seventy-fifth": 75, "seventy-sixth": 76, "seventy-seventh": 77,
    "seventy-eighth": 78, "seventy-ninth": 79, "eightieth": 80,
    "eighty-first": 81, "eighty-second": 82, "eighty-third": 83,
    "eighty-fourth": 84, "eighty-fifth": 85, "eighty-sixth": 86,
    "eighty-seventh": 87, "eighty-eighth": 88, "eighty-ninth": 89,
    "ninetieth": 90, "ninety-first": 91, "ninety-second": 92,
    "ninety-third": 93, "ninety-fourth": 94, "ninety-fifth": 95,
    "ninety-sixth": 96, "ninety-seventh": 97, "ninety-eighth": 98,
    "ninety-ninth": 99, "hundredth": 100,
}

ORDINAL_NUMBER_RE = re.compile(r"\b(\d+)[’']?(st|nd|rd|th)\b", re.IGNORECASE)

ROMAN_RE = re.compile(r"\b[IVXLCDM]+\b", re.IGNORECASE)
ROMAN_MAP = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str):
    s = s.upper()
    total = 0
    prev = 0
    for ch in reversed(s):
        if ch not in ROMAN_MAP:
            return None
        value = ROMAN_MAP[ch]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    if total <= 0 or total > 1000:
        return None
    return total


# --- proceedings noise stripping -------------------------------------

PROCEEDINGS_PREFIX_RE = re.compile(
    r"""
    ^\s*
    (?:
      proceedings \s+ of \s+ (the\s+)?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

PROCEEDINGS_TRAIL_RE = re.compile(
    r"""
    \s*,?\s*
    (?:
        proceedings? |
        conference\s+proceedings? |
        workshop\s+proceedings?
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_proceedings_noise(name: str) -> str:
    """
    Remove generic 'proceedings' wrappers that refer to the publication,
    not the conference name, e.g.:
      'Proceedings of the 7th IEEE ... Conference'
      'GlobalSIP 2019 - ... , Proceedings'
    """
    if not name:
        return name
    s = str(name).strip()

    # Remove leading "Proceedings of (the) "
    s = PROCEEDINGS_PREFIX_RE.sub("", s).strip()

    # Remove trailing ", proceedings" forms
    s = PROCEEDINGS_TRAIL_RE.sub("", s).strip(" ,")

    return s


def extract_conf_order(text: str):
    """
    Extracts the conference order number (e.g. 5 for 'Fifth International...',
    25 for 'XXV Nordic Concrete Research Symposium').
    Returns int or None.
    """
    if not text:
        return None
    t = str(text)

    m = ORDINAL_NUMBER_RE.search(t)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    words = re.findall(r"[A-Za-z\-]+", t)
    for w in words:
        key = w.lower()
        if key in ORDINAL_WORDS:
            return ORDINAL_WORDS[key]

    m_roman = ROMAN_RE.search(t)
    if m_roman:
        value = roman_to_int(m_roman.group(0))
        if value is not None:
            return value

    return None


# --- acronym + year patches -------------------------------------------

ACRONYM_YEAR_RE = re.compile(r"\b([A-Z]{2,})\s+(20\d{2}|19\d{2})\b")


def maybe_add_acronym_year_from_raw(raw: str, name: str) -> str:
    if not raw or not name:
        return name
    raw = str(raw)
    name = str(name)

    m = ACRONYM_YEAR_RE.search(raw)
    if not m:
        return name
    acro, year = m.group(1), m.group(2)

    if acro in name and f"{acro} {year}" not in name:
        return name.replace(acro, f"{acro} {year}", 1)
    return name


PAREN_ACRO_RE = re.compile(r"([A-Za-z0-9][^()]+?)\s*\(([A-Z]{2,})\)")


def maybe_keep_parenthesized_acronym_from_raw(raw: str, name: str) -> str:
    if not raw or not name:
        return name
    raw = str(raw)
    name = str(name)

    m = PAREN_ACRO_RE.search(raw)
    if not m:
        return name

    full, acro = m.group(1).strip(), m.group(2).strip()
    pattern_with_acro = f"{full} ({acro})"

    if pattern_with_acro in name:
        return name

    if full in name and f"{full} {acro}" not in name:
        return name.replace(full, pattern_with_acro, 1)

    return name
