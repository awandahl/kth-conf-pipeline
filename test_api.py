from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ParseRequest(BaseModel):
    raw: str

@app.post("/parse")
def parse_endpoint(req: ParseRequest):
    return {"ok": True, "len": len(req.raw)}
