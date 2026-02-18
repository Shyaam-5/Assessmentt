"""Code execution proxy (Piston API)."""

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["code_execution"])

PISTON_URL = "https://emkc.org/api/v2/piston/execute"

# Language → Piston version mapping
LANGUAGE_MAP = {
    "javascript": ("javascript", "18.15.0"),
    "python": ("python", "3.10.0"),
    "java": ("java", "15.0.2"),
    "cpp": ("c++", "10.2.0"),
    "c": ("c", "10.2.0"),
    "typescript": ("typescript", "5.0.3"),
    "go": ("go", "1.16.2"),
    "rust": ("rust", "1.68.2"),
    "ruby": ("ruby", "3.0.1"),
    "php": ("php", "8.2.3"),
    "sql": ("sqlite3", "3.36.0"),
    "sqlite3": ("sqlite3", "3.36.0"),
}


class RunRequest(BaseModel):
    language: str
    code: str
    input: str | None = ""


@router.post("/run")
async def run_code(body: RunRequest):
    lang_lower = body.language.lower()
    piston_lang, version = LANGUAGE_MAP.get(lang_lower, (lang_lower, "*"))

    payload = {
        "language": piston_lang,
        "version": version,
        "files": [{"content": body.code}],
    }
    if body.input:
        payload["stdin"] = body.input

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(PISTON_URL, json=payload)

    data = resp.json()
    run_info = data.get("run", {})

    return {
        "output": run_info.get("output", ""),
        "error": run_info.get("stderr", ""),
        "exitCode": run_info.get("code", 0),
    }
