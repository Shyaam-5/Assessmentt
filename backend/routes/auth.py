"""Authentication and user management routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import get_pool
import pymysql.cursors

router = APIRouter(prefix="/api", tags=["auth"])


# ---------- Request / Response models ----------

class LoginRequest(BaseModel):
    email: str
    password: str


# ---------- Helpers ----------

def _clean_user(row: dict) -> dict:
    """Strip password and normalise keys for the frontend."""
    u = dict(row)
    u.pop("password", None)
    u["mentorId"] = u.pop("mentor_id", None)
    u["createdAt"] = str(u.pop("created_at", ""))
    return u


# ---------- Routes ----------

@router.post("/auth/login")
async def login(body: LoginRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM users WHERE email = %s AND password = %s",
                (body.email, body.password),
            )
            row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = _clean_user(row)
    return {"success": True, "user": user}


@router.get("/users/{user_id}")
async def get_user(user_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return _clean_user(row)


@router.get("/users")
async def list_users(role: str | None = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            if role:
                await cur.execute(
                    """
                    SELECT u.*, GROUP_CONCAT(msa.student_id) AS allocated_students
                    FROM users u
                    LEFT JOIN mentor_student_allocations msa ON u.id = msa.mentor_id
                    WHERE u.role = %s
                    GROUP BY u.id
                    ORDER BY u.created_at DESC
                    """,
                    (role,),
                )
            else:
                await cur.execute(
                    """
                    SELECT u.*, GROUP_CONCAT(msa.student_id) AS allocated_students
                    FROM users u
                    LEFT JOIN mentor_student_allocations msa ON u.id = msa.mentor_id
                    GROUP BY u.id
                    ORDER BY u.created_at DESC
                    """
                )
            rows = await cur.fetchall()

    users = []
    for r in rows:
        u = _clean_user(r)
        alloc = r.get("allocated_students")
        if role == "mentor" and alloc:
            u["allocatedStudents"] = [s for s in alloc.split(",") if s]
        users.append(u)

    return users


@router.get("/mentors/{mentor_id}/students")
async def get_mentor_students(mentor_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute(
                'SELECT * FROM users WHERE role = "student" AND mentor_id = %s',
                (mentor_id,),
            )
            rows = await cur.fetchall()

    return [_clean_user(r) for r in rows]



