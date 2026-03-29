import json
import re
from config import MAX_SERIES_CANDIDATES
from llm_parse import stream_llm_json


def find_series_candidates(con, conf_name: str, max_candidates: int = MAX_SERIES_CANDIDATES):
    if not conf_name:
        return []

    tokens = re.findall(r"\b[A-Z]{3,}\b", conf_name)
    acronym = tokens[-1] if tokens else ""
    short = " ".join(conf_name.split()[:6])

    if acronym:
        query = """
            SELECT series_slug, stream_iri, series_name
            FROM dblp_conference_series
            WHERE lower(series_slug) = lower(?)
               OR series_name ILIKE ?
            LIMIT ?
        """
        params = [acronym.lower(), f"%{acronym}%", max_candidates]
    else:
        query = """
            SELECT series_slug, stream_iri, series_name
            FROM dblp_conference_series
            WHERE series_name ILIKE ?
            LIMIT ?
        """
        params = [f"%{short}%", max_candidates]

    return con.execute(query, params).fetchall()


def choose_series_with_llm(conf_name: str, conf_dates: str, candidates):
    if not candidates:
        return (None, None, None, "")

    cand_lines = []
    for i, (slug, iri, name) in enumerate(candidates, start=1):
        cand_lines.append(f"{i}. slug='{slug}', name='{name}'")
    cand_text = "\n".join(cand_lines)

    instruction = """
You are matching a cleaned conference instance to its conference series in the dblp knowledge graph.

You get:
- conf_name: normalized conference instance name
- conf_dates: normalized conference dates (if any)
- A small list of candidate conference series, each with slug and name.

Task:
- Choose the single best matching conference series from the candidate list.
- Prefer exact or near-exact matches on name and acronym, ignoring year and local edition.
- If no candidate is clearly appropriate, return chosen_index = null.

Respond ONLY as JSON, for example:
{
  "chosen_index": 1,
  "reason": "short explanation, max 20 words"
}
"""

    prompt = (
        instruction
        + f"\n\nconf_name: {conf_name}\n"
          f"conf_dates: {conf_dates}\n\n"
          "Candidates:\n"
        + cand_text
        + "\n\nJSON:"
    )

    text = stream_llm_json(prompt, show_stream=False)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return (None, None, None, "")

    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return (None, None, None, "")

    idx = obj.get("chosen_index")
    reason = str(obj.get("reason", "") or "")
    if not isinstance(idx, int) or idx < 1 or idx > len(candidates):
        return (None, None, None, reason)

    slug, iri, name = candidates[idx - 1]
    return (slug, iri, name, reason)
