"""Problem CRUD routes with proctoring settings."""

import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from database import get_pool
from services.pagination import paginated_response
import pymysql.cursors

router = APIRouter(prefix="/api", tags=["problems"])


class ProblemCreate(BaseModel):
    mentorId: str
    title: str
    description: str
    sampleInput: str | None = None
    expectedOutput: str | None = None
    difficulty: str = "medium"
    type: str = "coding"
    language: str | None = "javascript"
    status: str = "live"
    deadline: str | None = None
    # SQL-specific
    sqlSchema: str | None = None
    expectedQueryResult: str | None = None
    # Proctoring
    enableCamera: bool | None = False
    enableProctoring: bool | None = False
    enableAIProctoring: bool | None = False
    trackTabSwitches: bool | None = False
    maxTabSwitches: int | None = 3
    enableFaceDetection: bool | None = False
    detectMultipleFaces: bool | None = False
    trackFaceLookaway: bool | None = False


def _enrich_problem(p: dict) -> dict:
    """Normalise column names and attach proctoring settings."""
    p["mentorId"] = p.pop("mentor_id", None)
    p["sampleInput"] = p.pop("sample_input", None)
    p["expectedOutput"] = p.pop("expected_output", None)
    p["sqlSchema"] = p.pop("sql_schema", None)
    p["expectedQueryResult"] = p.pop("expected_query_result", None)
    p["createdAt"] = str(p.pop("created_at", ""))

    # Proctoring settings
    p["proctoringSettings"] = {
        "enableCamera": p.pop("enable_camera", None) == "true",
        "enableProctoring": p.pop("enable_proctoring", None) == "true",
        "enableAIProctoring": p.pop("enable_ai_proctoring", None) == "true",
        "trackTabSwitches": p.pop("track_tab_switches", None) == "true",
        "maxTabSwitches": int(p.pop("max_tab_switches", 3) or 3),
        "enableFaceDetection": p.pop("enable_face_detection", None) == "true",
        "detectMultipleFaces": p.pop("detect_multiple_faces", None) == "true",
        "trackFaceLookaway": p.pop("track_face_lookaway", None) == "true",
    }
    return p


@router.get("/problems")
async def list_problems(
    mentorId: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    pool = await get_pool()
    offset = (page - 1) * limit
    params: list = []
    where: list[str] = []

    if mentorId:
        where.append("p.mentor_id = %s")
        params.append(mentorId)
    if status:
        where.append("p.status = %s")
        params.append(status)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute(f"SELECT COUNT(*) AS total FROM problems p{where_sql}", params)
            total = (await cur.fetchone())["total"]

            await cur.execute(
                f"""
                SELECT p.*,
                       GROUP_CONCAT(DISTINCT pc.student_id) AS completed_by_students
                FROM problems p
                LEFT JOIN problem_completions pc ON p.id = pc.problem_id
                {where_sql}
                GROUP BY p.id
                ORDER BY p.created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = await cur.fetchall()

    problems = []
    for r in rows:
        cbs = r.pop("completed_by_students", None)
        p = _enrich_problem(r)
        p["completedBy"] = [s for s in cbs.split(",") if s] if cbs else []
        problems.append(p)

    return paginated_response(data=problems, total=total, page=page, limit=limit)


@router.get("/students/{student_id}/problems")
async def student_problems(student_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute("SELECT mentor_id FROM users WHERE id = %s", (student_id,))
            stu = await cur.fetchone()
            if not stu:
                raise HTTPException(404, "Student not found")

            mentor_id = stu["mentor_id"]
            await cur.execute(
                """SELECT * FROM problems
                   WHERE (mentor_id = %s OR mentor_id = 'admin-001') AND status = 'live'""",
                (mentor_id,),
            )
            problems = await cur.fetchall()

            enriched = []
            for p in problems:
                await cur.execute(
                    "SELECT student_id FROM problem_completions WHERE problem_id = %s",
                    (p["id"],),
                )
                completions = await cur.fetchall()
                ep = _enrich_problem(p)
                ep["completedBy"] = [c["student_id"] for c in completions]
                enriched.append(ep)

    return enriched


@router.post("/problems")
async def create_problem(body: ProblemCreate):
    problem_id = str(uuid.uuid4())
    now = datetime.utcnow()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO problems (
                    id, mentor_id, title, description, sample_input, expected_output,
                    difficulty, type, language, status, deadline,
                    sql_schema, expected_query_result,
                    enable_camera, enable_proctoring, enable_ai_proctoring,
                    track_tab_switches, max_tab_switches,
                    enable_face_detection, detect_multiple_faces, track_face_lookaway,
                    created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    problem_id, body.mentorId, body.title, body.description,
                    body.sampleInput, body.expectedOutput,
                    body.difficulty, body.type, body.language, body.status, body.deadline,
                    body.sqlSchema, body.expectedQueryResult,
                    str(body.enableCamera).lower(), str(body.enableProctoring).lower(),
                    str(body.enableAIProctoring).lower(),
                    str(body.trackTabSwitches).lower(), body.maxTabSwitches,
                    str(body.enableFaceDetection).lower(),
                    str(body.detectMultipleFaces).lower(),
                    str(body.trackFaceLookaway).lower(),
                    now,
                ),
            )

    return {"id": problem_id, **body.model_dump(), "completedBy": [], "createdAt": str(now)}


@router.delete("/problems/{problem_id}")
async def delete_problem(problem_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM problem_completions WHERE problem_id = %s", (problem_id,))
            await cur.execute("DELETE FROM submissions WHERE problem_id = %s", (problem_id,))
            await cur.execute("DELETE FROM problems WHERE id = %s", (problem_id,))
    return {"success": True}
