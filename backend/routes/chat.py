"""AI chatbot route."""

from fastapi import APIRouter
from pydantic import BaseModel
from services.ai_service import cerebras_chat

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    context: str | None = ""
    history: list[dict] | None = None


@router.post("/chat")
async def chat(body: ChatRequest):
    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI coding assistant for a mentoring platform. "
                "Help students with programming concepts, debugging, and best practices. "
                "Be encouraging and educational. If the student shares code, provide constructive feedback."
            ),
        }
    ]

    if body.history:
        messages.extend(body.history[-10:])  # keep last 10 messages for context

    if body.context:
        messages.append({"role": "user", "content": f"Context: {body.context}"})

    messages.append({"role": "user", "content": body.message})

    try:
        resp = await cerebras_chat(messages, temperature=0.7, max_tokens=1024)
        reply = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"reply": reply, "success": True}
    except Exception as e:
        return {"reply": "Sorry, I'm having trouble responding right now.", "success": False, "error": str(e)}
