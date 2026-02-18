"""AI-powered hint generation route."""

from fastapi import APIRouter
from pydantic import BaseModel
from services.ai_service import cerebras_chat

router = APIRouter(prefix="/api", tags=["hints"])


class HintRequest(BaseModel):
    problemTitle: str | None = ""
    problemDescription: str | None = ""
    language: str | None = "javascript"
    currentCode: str | None = ""
    difficulty: str | None = "medium"


@router.post("/hints")
async def generate_hint(body: HintRequest):
    prompt = f"""You are a helpful coding tutor. A student is stuck on a problem.

Problem: {body.problemTitle}
Description: {body.problemDescription}
Language: {body.language}
Difficulty: {body.difficulty}

Their current code:
{body.currentCode or '(no code written yet)'}

Give a helpful hint WITHOUT giving the full solution. Guide them toward the right approach.
Keep the hint concise (2-4 sentences). Focus on the conceptual approach, not the exact code."""

    try:
        resp = await cerebras_chat(
            [
                {"role": "system", "content": "You are a coding tutor. Give hints, not solutions."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=300,
        )
        hint = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"hint": hint, "success": True}
    except Exception as e:
        return {"hint": "Sorry, hint generation failed. Try breaking the problem into smaller parts.", "success": False, "error": str(e)}
