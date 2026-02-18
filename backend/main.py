"""FastAPI application entry-point with CORS, Socket.io, and all route modules."""

import os
import socketio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db, close_db

# ─── Socket.io ──────────────────────────────────────────────────

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)

# Connected monitoring clients
monitors: dict[str, list] = {"admins": {}, "mentors": {}, "students": {}}


@sio.event
async def connect(sid, environ):
    print(f"[Socket] Connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"[Socket] Disconnected: {sid}")


@sio.event
async def join_monitoring(sid, data):
    user_id = data.get("userId")
    role = data.get("role")
    mentor_id = data.get("mentorId")
    if role == "admin":
        await sio.enter_room(sid, "admin_room")
    elif role == "mentor" and mentor_id:
        await sio.enter_room(sid, f"mentor_{mentor_id}")
    await sio.emit("monitoring_connected", {"userId": user_id, "role": role}, to=sid)


@sio.event
async def submission_started(sid, data):
    mentor_id = data.get("mentorId")
    await sio.emit("live_update", {**data, "type": "submission_started"}, room="admin_room")
    if mentor_id:
        await sio.emit("live_update", {**data, "type": "submission_started"}, room=f"mentor_{mentor_id}")


@sio.event
async def submission_completed(sid, data):
    mentor_id = data.get("mentorId")
    await sio.emit("live_update", {**data, "type": "submission_completed"}, room="admin_room")
    if mentor_id:
        await sio.emit("live_update", {**data, "type": "submission_completed"}, room=f"mentor_{mentor_id}")


@sio.event
async def proctoring_violation(sid, data):
    mentor_id = data.get("mentorId")
    await sio.emit("live_alert", {**data, "type": "proctoring_violation"}, room="admin_room")
    if mentor_id:
        await sio.emit("live_alert", {**data, "type": "proctoring_violation"}, room=f"mentor_{mentor_id}")


@sio.event
async def progress_update(sid, data):
    mentor_id = data.get("mentorId")
    await sio.emit("live_update", {**data, "type": "progress_update"}, room="admin_room")
    if mentor_id:
        await sio.emit("live_update", {**data, "type": "progress_update"}, room=f"mentor_{mentor_id}")


@sio.event
async def test_failed(sid, data):
    mentor_id = data.get("mentorId")
    await sio.emit("live_alert", {**data, "type": "test_failed"}, room="admin_room")
    if mentor_id:
        await sio.emit("live_alert", {**data, "type": "test_failed"}, room=f"mentor_{mentor_id}")


# ─── FastAPI lifespan ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print("[OK] FastAPI server started.")
    yield
    # Shutdown
    await close_db()
    print("[OK] FastAPI server shut down.")


# ─── Create App ─────────────────────────────────────────────────

app = FastAPI(title="MentorHub API", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite frontend
        "http://localhost:8000",    # Self
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Register routes ────────────────────────────────────────────

from routes.auth import router as auth_router
from routes.tasks import router as tasks_router
from routes.problems import router as problems_router
from routes.submissions import router as submissions_router
from routes.code_execution import router as code_exec_router
from routes.hints import router as hints_router
from routes.chat import router as chat_router
from routes.messaging import router as messaging_router
from routes.analytics import router as analytics_router
from routes.skill_tests import router as skill_tests_router

app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(problems_router)
app.include_router(submissions_router)
app.include_router(code_exec_router)
app.include_router(hints_router)
app.include_router(chat_router)
app.include_router(messaging_router)
app.include_router(analytics_router)
app.include_router(skill_tests_router)


# ─── Health check ────────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "MentorHub FastAPI is running"}


# ─── Uploads static files ───────────────────────────────────────

uploads_dir = os.path.join(os.path.dirname(__file__), "uploads", "proctoring")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "uploads")), name="uploads")


# ─── Wrap with Socket.io ASGI app ──────────────────────────────

socket_app = socketio.ASGIApp(sio, app)


# ─── Entry-point ─────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:socket_app", host="0.0.0.0", port=port, reload=True)
