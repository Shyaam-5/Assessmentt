"""Direct messaging routes."""

import uuid
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from database import get_pool
import pymysql.cursors

router = APIRouter(prefix="/api", tags=["messaging"])


class MessageSend(BaseModel):
    senderId: str
    receiverId: str
    content: str


@router.get("/messages/{user_id}")
async def get_conversations(user_id: str):
    """Get all unique conversations for a user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            await cur.execute(
                """
                SELECT DISTINCT
                    CASE WHEN sender_id = %s THEN receiver_id ELSE sender_id END AS other_user_id
                FROM direct_messages
                WHERE sender_id = %s OR receiver_id = %s
                """,
                (user_id, user_id, user_id),
            )
            conversations = await cur.fetchall()

            result = []
            for c in conversations:
                other_id = c["other_user_id"]
                await cur.execute("SELECT id, name, email, role FROM users WHERE id = %s", (other_id,))
                user = await cur.fetchone()

                await cur.execute(
                    """SELECT * FROM direct_messages
                       WHERE (sender_id = %s AND receiver_id = %s) OR (sender_id = %s AND receiver_id = %s)
                       ORDER BY created_at DESC LIMIT 1""",
                    (user_id, other_id, other_id, user_id),
                )
                last_msg = await cur.fetchone()

                await cur.execute(
                    "SELECT COUNT(*) AS cnt FROM direct_messages WHERE sender_id = %s AND receiver_id = %s AND is_read = 0",
                    (other_id, user_id),
                )
                unread = (await cur.fetchone())["cnt"]

                result.append({
                    "userId": other_id,
                    "name": user["name"] if user else "Unknown",
                    "role": user["role"] if user else "",
                    "lastMessage": last_msg["content"] if last_msg else "",
                    "lastMessageAt": str(last_msg["created_at"]) if last_msg else "",
                    "unreadCount": unread,
                })

    return result


@router.get("/messages/{user_id}/{other_user_id}")
async def get_messages(user_id: str, other_user_id: str):
    """Get messages between two users."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Mark messages as read
            await cur.execute(
                "UPDATE direct_messages SET is_read = 1 WHERE sender_id = %s AND receiver_id = %s AND is_read = 0",
                (other_user_id, user_id),
            )

            await cur.execute(
                """SELECT dm.*, u.name AS sender_name FROM direct_messages dm
                   JOIN users u ON dm.sender_id = u.id
                   WHERE (dm.sender_id = %s AND dm.receiver_id = %s) OR (dm.sender_id = %s AND dm.receiver_id = %s)
                   ORDER BY dm.created_at ASC LIMIT 100""",
                (user_id, other_user_id, other_user_id, user_id),
            )
            rows = await cur.fetchall()

    return [
        {
            "id": m["id"],
            "senderId": m["sender_id"],
            "senderName": m["sender_name"],
            "receiverId": m["receiver_id"],
            "content": m["content"],
            "isRead": bool(m["is_read"]),
            "createdAt": str(m["created_at"]),
        }
        for m in rows
    ]


@router.post("/messages")
async def send_message(body: MessageSend):
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO direct_messages (id, sender_id, receiver_id, content, is_read, created_at) VALUES (%s,%s,%s,%s,0,%s)",
                (msg_id, body.senderId, body.receiverId, body.content, now),
            )

    return {"id": msg_id, "senderId": body.senderId, "receiverId": body.receiverId, "content": body.content, "createdAt": str(now)}
