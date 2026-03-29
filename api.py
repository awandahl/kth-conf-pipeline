from fastapi import FastAPI
from pydantic import BaseModel
from conf.llm_parse import parse_with_llm  # adjust if needed

app = FastAPI()

class ParseRequest(BaseModel):
    raw: str

@app.post("/parse")
def parse_endpoint(req: ParseRequest):
    parsed = parse_with_llm(req.raw, show_stream=False)
    return parsed
