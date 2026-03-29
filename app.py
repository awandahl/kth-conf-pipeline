from flask import Flask, request, jsonify
import sys
sys.path.append('/home/aw/production/conf')
from llm_api import parse_conference_string

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/parse", methods=["POST"])
def parse():
    data = request.get_json(force=True) or {}
    raw = data.get("conference", "")
    show_stream = bool(data.get("show_stream", False))

    if not raw.strip():
        return jsonify({"error": "missing conference"}), 400

    result = parse_conference_string(raw, show_stream=show_stream)
    return jsonify(result)
