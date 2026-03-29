# KTH Conference Parser

This project parses free-text conference descriptions into structured conference metadata and exposes that functionality via a small Flask + Gunicorn HTTP API. It is deployed behind nginx on `conf.vm-app.cloud.cbh.kth.se` and backed by a DuckDB database.

## High-level architecture

- **Frontend**  
  - Served by nginx from `/var/www/conf`  
  - Browser calls `POST /api/parse` on the same host

- **nginx**  
  - Serves the static frontend  
  - Proxies `/api/` to Gunicorn/Flask on `127.0.0.1:8000`

- **HTTP API (this repo)**  
  - Location: `/home/aw/production/conf`  
  - Entrypoint: `app.py` (Flask app)  
  - WSGI server: Gunicorn, managed by systemd (`llm-api.service`)

- **Parsing engine**  
  - Wrapper: `llm_api.py`  
  - Core logic: `llm_parse.py` (delegates to the local LLM via `OLLAMA_URL`, `MODEL`, etc.)  
  - Supporting modules: `regex_utils.py`, `pipeline.py`, `db_io.py`, `fast_llm_parse.py`, etc.  
  - Data: `kth_metadata.duckdb`, `dblp_conference_series.csv`

## Repository layout (selected files)

- `app.py` – Flask HTTP API (`/health`, `/parse`)
- `llm_api.py` – Thin wrapper exposing `parse_conference_string()`
- `llm_parse.py` – Main LLM-based conference parsing logic
- `pipeline.py` – Batch parsing pipeline and enrichment
- `regex_utils.py` – Regex helpers for normalization/parsing
- `db_io.py` – DuckDB I/O utilities
- `kth_metadata.duckdb` – Main DuckDB database
- `dblp_conference_series.csv` – DBLP conference series metadata

## API

All HTTP paths are exposed under `/api/` externally via nginx, and directly under `/` on the Flask app.

### Health check

- **Endpoint:** `GET /api/health`  
- **Response:**
  ```json
  { "status": "ok" }
  ```

### Parse conference string

- **Endpoint:** `POST /api/parse`  
- **Request JSON:**
  ```json
  {
    "conference": "raw free-text conference string",
    "show_stream": false
  }
  ```

- **Validation:**
  - If `conference` is missing or blank, returns `400` with:
    ```json
    { "error": "missing conference" }
    ```

- **Success response:**
  The API returns a JSON object with this canonical schema. All keys SHOULD be present; some may be empty strings when unknown:

  ```json
  {
    "conf_name": "",
    "conf_place": "",
    "conf_dates": "",
    "conf_start_date": "",
    "conf_end_date": "",
    "conf_code": "",
    "conf_order": "",
    "conf_concat": "",
    "note": ""
  }
  ```

  **Field meanings:**

  - `conf_name` – Parsed conference name (normalized, edition stripped where possible)  
  - `conf_place` – Parsed conference place (city/region string)  
  - `conf_dates` – Human-readable date span (e.g. `"2024-07-03 / 2024-07-07"`)  
  - `conf_start_date` – Start date, machine-friendly string (ISO-style)  
  - `conf_end_date` – End date, machine-friendly string (ISO-style)  
  - `conf_code` – Short code for the conference series (placeholder for future use)  
  - `conf_order` – Edition/order number for this conference instance  
  - `conf_concat` – Pretty concatenation of name, place, and dates for display  
  - `note` – Parser note/explanation (e.g. uncertainty, assumptions)

Internally, `app.py` calls `parse_conference_string()` from `llm_api.py`, which then delegates to `parse_with_llm()` in `llm_parse.py`. The batch pipeline (`pipeline.py`) can further enrich and persist results into DuckDB.

## Runtime environment

- **User:** `aw`
- **Repo path:** `/home/aw/production/conf`
- **Python:** system-wide venv at `/home/aw/venv`
- **Database:** `/home/aw/production/conf/kth_metadata.duckdb`

The recommended way to work with the project is:

```bash
cd /home/aw/production/conf
source /home/aw/venv/bin/activate
python app.py   # for local/manual testing
```

## Systemd service

The production API is run via `systemd` + Gunicorn. The service unit is:

```ini
[Unit]
Description=Gunicorn LLM Flask API
After=network.target

[Service]
User=aw
Group=www-data
WorkingDirectory=/home/aw/production/conf
Environment="PATH=/home/aw/venv/bin"
ExecStart=/home/aw/venv/bin/gunicorn \
  -b 127.0.0.1:8000 \
  --timeout 120 \
  app:app

[Install]
WantedBy=multi-user.target
```

After changes to the service or code, reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart llm-api.service
sudo systemctl status llm-api.service
```

## nginx integration (summary)

On the server, nginx:

- Serves the frontend from `/var/www/conf`
- Proxies API calls to Gunicorn:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Prefix /api;
    proxy_read_timeout 300;
    proxy_connect_timeout 60;
    proxy_send_timeout 300;
}
```

The browser should always call `/api/parse` and `/api/health` (not the bare `/parse` path).

## Development notes

- Always work inside the venv: `source /home/aw/venv/bin/activate`
- Keep the canonical metadata schema in sync across:
  - `llm_parse.py` (LLM output)
  - `llm_api.py` (normalization and default values)
  - `app.py` (HTTP responses)
  - `pipeline.py` / DuckDB schemas
- For new fields, first update the schema in this README, then make consistent changes in:
  - parser code
  - API wrapper
  - database/pipeline
  - frontend display
