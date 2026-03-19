"""AI generation & chat routes used by AdminPortal and AIChatbot."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any
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
    section: str = "aptitude"


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

    def _normalize_coding_problem(problem: Any) -> dict:
        p = problem if isinstance(problem, dict) else {}
        lang = (body.language or "Python").strip()

        title = str(p.get("title") or "").strip()
        description = str(p.get("description") or p.get("question") or "").strip()
        question = str(p.get("question") or "").strip()
        if not question:
            question = f"{title}\n\n{description}".strip() if title and description else (description or title)

        # Starter code can come as starter_code dict keyed by language.
        starter_raw = p.get("starterCode", p.get("starter_code", ""))
        starter_code = ""
        if isinstance(starter_raw, dict):
            key_map = {
                "python": "python",
                "javascript": "javascript",
                "java": "java",
                "c++": "cpp",
                "cpp": "cpp",
            }
            lk = key_map.get(lang.lower(), "python")
            starter_code = str(starter_raw.get(lk) or starter_raw.get("python") or "").strip()
            if not starter_code:
                # fallback to first non-empty snippet
                for _, v in starter_raw.items():
                    if str(v or "").strip():
                        starter_code = str(v).strip()
                        break
        else:
            starter_code = str(starter_raw or "").strip()

        # Test cases can be test_cases list OR testCases.cases object
        raw_cases = p.get("testCases", p.get("test_cases", []))
        if isinstance(raw_cases, dict):
            raw_cases = raw_cases.get("cases", [])
        cases: list[dict] = []
        if isinstance(raw_cases, list):
            for tc in raw_cases:
                if not isinstance(tc, dict):
                    continue
                inp = str(tc.get("input", ""))
                out = str(tc.get("expected_output", tc.get("expectedOutput", "")))
                if inp.strip() or out.strip():
                    cases.append({"input": inp, "expected_output": out})

        # Add sample pair as fallback case if no explicit cases provided.
        if not cases:
            s_in = str(p.get("sample_input", p.get("sampleInput", "")))
            s_out = str(p.get("sample_output", p.get("sampleOutput", "")))
            if s_in.strip() or s_out.strip():
                cases.append({"input": s_in, "expected_output": s_out})

        difficulty = str(p.get("difficulty") or body.difficulty or "Medium").strip().capitalize()
        if difficulty not in ("Easy", "Medium", "Hard"):
            difficulty = "Medium"

        return {
            "question": question,
            "title": title,
            "description": description,
            "starterCode": starter_code,
            "testCases": cases,
            "language": lang,
            "difficulty": difficulty,
            "hints": p.get("hints") if isinstance(p.get("hints"), list) else [],
            "solutionCode": str(p.get("solutionCode", p.get("solution_code", "")) or ""),
            "timeLimit": int(p.get("time_limit_seconds") or p.get("timeLimit") or 0),
        }

    try:
        problems = await generate_coding_problems(
            skills, count=1, difficulty_level=body.difficulty.lower(),
        )
        if problems:
            return {"problem": _normalize_coding_problem(problems[0])}
        return {"problem": _normalize_coding_problem({"question": f"Write a {body.language} program to solve: {body.topic}"})}
    except Exception as exc:
        return {
            "problem": _normalize_coding_problem({
                "question": f"Write a {body.language} program to solve: {body.topic}",
                "difficulty": body.difficulty,
            }),
            "error": str(exc),
        }


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
    section = (body.section or "aptitude").strip().lower()
    if section not in ("aptitude", "verbal", "logical"):
        section = "aptitude"

    count = max(1, min(int(body.count or 5), 20))
    difficulty = (body.difficulty or "Medium").strip().lower()
    topic = (body.topic or "").strip()

    section_focus = {
        "aptitude": "quantitative aptitude, percentages, ratios, speed-time-distance, profit-loss, data interpretation",
        "verbal": "grammar, vocabulary, sentence correction, reading comprehension, synonyms/antonyms",
        "logical": "logical reasoning, patterns, syllogisms, coding-decoding, puzzles, analytical reasoning",
    }

    system_prompt = (
        "You are an assessment item writer for competitive exams. "
        "Generate high-quality MCQs with one unambiguous correct option. "
        "Return ONLY valid JSON array with EXACT keys: question, options, correctAnswer, category, explanation. "
        "Rules: options must be exactly 4 strings, correctAnswer must be integer 0-3, explanation short and precise."
    )

    user_prompt = (
        f"Generate exactly {count} {difficulty} difficulty MCQs for section '{section}'. "
        f"Focus areas: {section_focus[section]}. "
        f"Topic hint: {topic or 'general'}\n"
        "Avoid technical/software programming questions. "
        "Avoid duplicates. "
        "Return only JSON array."
    )

    def normalize_questions(rows: Any) -> list[dict]:
        if not isinstance(rows, list):
            return []
        out: list[dict] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            q_text = str(r.get("question", "")).strip()
            if not q_text:
                continue
            opts = r.get("options") if isinstance(r.get("options"), list) else []
            opts = [str(o).strip() for o in opts if str(o).strip()]
            while len(opts) < 4:
                opts.append("")
            opts = opts[:4]

            raw_correct = r.get("correctAnswer", r.get("correct_answer", 0))
            correct_idx = 0
            if isinstance(raw_correct, int):
                correct_idx = raw_correct if 0 <= raw_correct <= 3 else 0
            elif isinstance(raw_correct, str):
                s = raw_correct.strip()
                if s.isdigit() and 0 <= int(s) <= 3:
                    correct_idx = int(s)
                else:
                    ix = next((i for i, o in enumerate(opts) if o == s), -1)
                    correct_idx = ix if ix >= 0 else 0

            out.append({
                "question": q_text,
                "options": opts,
                "correctAnswer": correct_idx,
                "category": str(r.get("category", section)).strip() or section,
                "explanation": str(r.get("explanation", "")).strip(),
            })
            if len(out) >= count:
                break
        return out

    try:
        raw = await _call_cerebras(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.7,
            max_tokens=5000,
        )
        parsed = parse_json(raw)
        normalized = normalize_questions(parsed)
        if normalized:
            return {"questions": normalized}

        # Fallback to legacy generator if model output malformed
        skills = [s.strip() for s in topic.split(",") if s.strip()] or [section]
        legacy = await generate_mcq_questions(skills, count=count)
        return {"questions": normalize_questions(legacy)}
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