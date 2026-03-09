"""AI generation routes for problems and tasks."""

import json
from fastapi import APIRouter
from pydantic import BaseModel
from services.ai_service import cerebras_chat, parse_json

router = APIRouter(prefix="/api/ai", tags=["ai"])

class GenerateRequest(BaseModel):
    prompt: str
    type: str = "problem" # "task" or "problem"
    language: str | None = "Python"

class AIChatRequest(BaseModel):
    messages: list[dict]
    context: str = "problem"

@router.post("/generate-problem")
async def generate_problem(req: GenerateRequest):
    """Generate a structured coding problem or ML task using AI."""
    
    if req.type == "task":
        prompt = f"""You are an AI tasked with creating a detailed Machine Learning / Data Science task based on this request: "{req.prompt}".
Create a comprehensive, professional task specification. 
Respond ONLY with a valid JSON file using exactly this structure:
{{
    "title": "A short, engaging title",
    "type": "e.g., Sentiment Analysis, Image Classification",
    "difficulty": "Easy, Medium, or Hard",
    "description": "2-3 paragraphs explaining the real-world scenario and goal of the task",
    "requirements": "A bulleted list format string of specific requirements or evaluation metrics"
}}"""
    elif req.language and req.language.lower() == "sql":
        prompt = f"""You are an AI tasked with creating a detailed SQL Database problem based on this request: "{req.prompt}".
Create a comprehensive, professional SQL query problem.
Respond ONLY with a valid JSON file using exactly this structure:
{{
    "title": "A short, engaging title",
    "type": "SQL",
    "difficulty": "Easy, Medium, or Hard",
    "description": "Clear explanation of the scenario and what the student needs to query",
    "sqlSchema": "The exact SQL CREATE TABLE and optional INSERT statements to set up the environment",
    "expectedQueryResult": "An example or textual representation of what the resulting rows should look like"
}}"""
    else:
        prompt = f"""You are an AI tasked with creating a detailed {req.language} coding problem based on this request: "{req.prompt}".
Create a comprehensive algorithmic or practical programming challenge.
Respond ONLY with a valid JSON file using exactly this structure:
{{
    "title": "A short, engaging title",
    "language": "{req.language}",
    "difficulty": "Easy, Medium, or Hard",
    "description": "Clear explanation of the problem, constraints, and goal",
    "sampleInput": "An exact string representing typical input data",
    "expectedOutput": "The exact expected printed output"
}}"""

    messages = [{"role": "user", "content": prompt}]
    
    try:
        resp = await cerebras_chat(messages, temperature=0.7, max_tokens=2048)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        generated = parse_json(content)
        
        if generated:
            return {"success": True, "generated": generated}
        else:
            return {"success": False, "error": "AI returned malformed JSON."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/chat")
async def ai_chat(req: AIChatRequest):
    """Conversational AI chat for brainstorming problems/tasks."""
    
    system_msg = "You are an AI assistant helping a mentor/admin brainstorm and create "
    if req.context == "task":
        system_msg += "Machine Learning and AI project tasks. You can help design datasets, models, and evaluation metrics."
    else:
        system_msg += "Algorithms, Data Structures, and SQL coding problems. "
        
    system_msg += " Be concise, helpful, and creative. Do not generate raw JSON unless specifically asked, just converse."

    chat_messages = [{"role": "system", "content": system_msg}]
    
    # Add user history
    for msg in req.messages[-6:]: # Keep last 6 to avoid context limits
        chat_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    try:
        resp = await cerebras_chat(chat_messages, temperature=0.7, max_tokens=1024)
        reply = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"response": reply, "generatedContent": None, "success": True}
    except Exception as e:
        return {"response": "Sorry, I encountered an error fulfilling your request.", "success": False, "error": str(e)}
