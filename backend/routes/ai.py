"""AI generation & chat routes used by AdminPortal and AIChatbot."""

from fastapi import APIRouter
from pydantic import BaseModel
from services.ai_service import (
    cerebras_chat,
    _call_cerebras,
    parse_json,
    generate_coding_problems,
    generate_sql_problems,
    generate_mcq_questions,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ─── Request / Response Models ──────────────────────────────────────────


class GenerateProblemRequest(BaseModel):
    prompt: str
    type: str = "problem"          # "problem" | "task"
    language: str = "Python"


class GenerateCodingProblemRequest(BaseModel):
    topic: str = ""
    difficulty: str = "Medium"
    language: str = "Python"


class GenerateSQLProblemRequest(BaseModel):
    topic: str = ""
    difficulty: str = "Medium"


class GenerateAptitudeRequest(BaseModel):
    topic: str = ""
    difficulty: str = "Medium"
    count: int = 5


class AIChatRequest(BaseModel):
    messages: list[dict]
    context: str = "problem"


# ─── Helpers ─────────────────────────────────────────────────────────────


_CODING_SYSTEM = (
    "You are an expert coding challenge designer. "
    "Given the user's request, generate a single coding problem. "
    "Return ONLY valid JSON with these fields:\n"
    '- "title": string\n'
    '- "description": string (clear problem statement)\n'
    '- "difficulty": "Easy" | "Medium" | "Hard"\n'
    '- "language": string\n'
    '- "sampleInput": string\n'
    '- "expectedOutput": string\n'
    '- "starterCode": string\n'
    '- "testCases": array of {input, expectedOutput}\n'
)

_SQL_SYSTEM = (
    "You are an expert SQL instructor. "
    "Given the user's request, generate a single SQL problem. "
    "Return ONLY valid JSON with these fields:\n"
    '- "title": string\n'
    '- "description": string\n'
    '- "difficulty": "Easy" | "Medium" | "Hard"\n'
    '- "type": "SQL"\n'
    '- "language": "SQL"\n'
    '- "sqlSchema": string (CREATE TABLE statements)\n'
    '- "expectedQueryResult": string (expected result preview)\n'
    '- "sampleInput": string (the query task)\n'
    '- "expectedOutput": string\n'
)

_TASK_SYSTEM = (
    "You are an expert ML/AI task designer for a mentoring platform. "
    "Given the user's request, generate a single ML/AI task. "
    "Return ONLY valid JSON with these fields:\n"
    '- "title": string\n'
    '- "type": string (e.g. "Classification", "NLP", "Computer Vision")\n'
    '- "difficulty": "Easy" | "Medium" | "Hard"\n'
    '- "description": string\n'
    '- "requirements": string (bullet-point list)\n'
)


# ─── Routes ──────────────────────────────────────────────────────────────


@router.post("/generate-problem")
async def generate_problem(body: GenerateProblemRequest):
    """Generate a single problem/task from a free-text prompt (AIChatbot)."""
    is_sql = body.language.upper() == "SQL"

    if body.type == "task":
        system_prompt = _TASK_SYSTEM
    elif is_sql:
        system_prompt = _SQL_SYSTEM
    else:
        system_prompt = _CODING_SYSTEM

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.prompt},
    ]

    try:
        raw = await _call_cerebras(messages, temperature=0.8, max_tokens=4096)
        generated = parse_json(raw)
        if generated and isinstance(generated, dict):
            if is_sql:
                generated.setdefault("type", "SQL")
                generated.setdefault("language", "SQL")
            elif body.type != "task":
                generated.setdefault("language", body.language)
            return {"success": True, "generated": generated}
        return {"success": False, "error": "Failed to parse AI response"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.post("/generate-coding-problem")
async def generate_coding_problem(body: GenerateCodingProblemRequest):
    """Generate a coding problem for the admin problem bank."""
    skills = [s.strip() for s in body.topic.split(",") if s.strip()] or [body.language]

    try:
        problems = await generate_coding_problems(
            skills, count=1, difficulty_level=body.difficulty.lower(),
        )
        if problems:
            problem = problems[0]
            problem.setdefault("language", body.language)
            return {"problem": problem}
        return {"error": "Generation failed"}, 500
    except Exception as exc:
        return {"error": str(exc)}, 500


@router.post("/generate-sql-problem")
async def generate_sql_problem(body: GenerateSQLProblemRequest):
    """Generate a SQL problem for the admin problem bank."""
    skills = [s.strip() for s in body.topic.split(",") if s.strip()] or ["SQL"]

    try:
        problems = await generate_sql_problems(skills, count=1)
        if problems:
            return {"problem": problems[0]}
        return {"error": "Generation failed"}, 500
    except Exception as exc:
        return {"error": str(exc)}, 500


@router.post("/generate-aptitude")
async def generate_aptitude(body: GenerateAptitudeRequest):
    """Generate aptitude / MCQ questions."""
    skills = [s.strip() for s in body.topic.split(",") if s.strip()] or ["general"]

    try:
        questions = await generate_mcq_questions(skills, count=body.count)
        return {"questions": questions}
    except Exception as exc:
        return {"questions": [], "error": str(exc)}


@router.post("/chat")
async def ai_chat(body: AIChatRequest):
    """Conversational AI chat with optional problem generation detection."""
    system_content = (
        "You are an AI coding assistant for a mentoring platform. "
        "Help users with programming concepts, problem creation, debugging, and best practices. "
        "Be encouraging and educational. "
        "If the user asks you to create or generate a problem, include a JSON block in your "
        "response with the problem specification."
    )

    messages = [{"role": "system", "content": system_content}]
    for m in body.messages[-10:]:
        messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    try:
        raw = await _call_cerebras(messages, temperature=0.7, max_tokens=2048)

        generated_content = None
        parsed = parse_json(raw)
        if parsed and isinstance(parsed, dict) and "title" in parsed:
            generated_content = parsed

        return {"response": raw, "generatedContent": generated_content, "success": True}
    except Exception as exc:
        return {
            "response": "Sorry, I'm having trouble responding right now.",
            "generatedContent": None,
            "success": False,
            "details": str(exc),
        }