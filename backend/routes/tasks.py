"""Task CRUD routes."""

import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from database import get_pool
from services.pagination import paginated_response
import pymysql.cursors

router = APIRouter(prefix="/api", tags=["tasks"])


class TaskCreate(BaseModel):
    mentorId: str
    title: str
    description: str
    requirements: str | None = None
    difficulty: str | None = "medium"
    type: str | None = "general"


@router.get("/tasks")
async def list_tasks(
    mentorId: str | None = None,
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    pool = await get_pool()
    offset = (page - 1) * limit
    params: list = []

    where_clauses: list[str] = []
    if mentorId:
        where_clauses.append("t.mentor_id = %s")
        params.append(mentorId)
    if status:
        where_clauses.append("t.status = %s")
        params.append(status)

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute(f"SELECT COUNT(*) AS total FROM tasks t{where_sql}", params)
            total = (await cur.fetchone())["total"]

            await cur.execute(
                f"""
                SELECT t.*,
                       GROUP_CONCAT(DISTINCT tc.student_id) AS completed_by_students
                FROM tasks t
                LEFT JOIN task_completions tc ON t.id = tc.task_id
                {where_sql}
                GROUP BY t.id
                ORDER BY t.created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = await cur.fetchall()

    tasks = []
    for t in rows:
        t["mentorId"] = t.pop("mentor_id", None)
        t["createdAt"] = str(t.pop("created_at", ""))
        cbs = t.pop("completed_by_students", None)
        t["completedBy"] = [s for s in cbs.split(",") if s] if cbs else []
        tasks.append(t)

    return paginated_response(data=tasks, total=total, page=page, limit=limit)


@router.get("/students/{student_id}/tasks")
async def student_tasks(student_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute("SELECT mentor_id FROM users WHERE id = %s", (student_id,))
            stu = await cur.fetchone()
            if not stu:
                raise HTTPException(404, "Student not found")

            mentor_id = stu["mentor_id"]
            await cur.execute(
                "SELECT * FROM tasks WHERE mentor_id = %s ORDER BY created_at DESC",
                (mentor_id,),
            )
            tasks = await cur.fetchall()

            enriched = []
            for t in tasks:
                await cur.execute(
                    "SELECT student_id FROM task_completions WHERE task_id = %s",
                    (t["id"],),
                )
                completions = await cur.fetchall()
                t["mentorId"] = t.pop("mentor_id", None)
                t["createdAt"] = str(t.pop("created_at", ""))
                t["completedBy"] = [c["student_id"] for c in completions]
                enriched.append(t)

    return enriched


@router.post("/tasks")
async def create_task(body: TaskCreate):
    task_id = str(uuid.uuid4())
    now = datetime.utcnow()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO tasks (id, mentor_id, title, description, requirements,
                   difficulty, type, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s)""",
                (
                    task_id,
                    body.mentorId,
                    body.title,
                    body.description,
                    body.requirements,
                    body.difficulty,
                    body.type,
                    now,
                ),
            )

    return {
        "id": task_id,
        "mentorId": body.mentorId,
        "title": body.title,
        "description": body.description,
        "requirements": body.requirements,
        "difficulty": body.difficulty,
        "type": body.type,
        "completedBy": [],
        "createdAt": str(now),
    }


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM task_completions WHERE task_id = %s", (task_id,))
            await cur.execute("DELETE FROM submissions WHERE task_id = %s", (task_id,))
            await cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
    return {"success": True}
