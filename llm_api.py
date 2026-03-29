# /home/aw/production/conf/llm_api.py
import os
import sys

BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from llm_parse import parse_with_llm  # uses your OLLAMA_URL, MODEL, etc.

def parse_conference_string(raw: str, show_stream: bool = False) -> dict:
    if raw is None:
        return {
            "conf_name": "",
            "conf_place": "",
            "conf_dates": "",
            "note": "no input",
        }

    # delegate to your existing LLM logic
    return parse_with_llm(raw, show_stream=show_stream)
