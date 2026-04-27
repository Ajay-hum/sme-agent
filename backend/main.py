import sys
import os
import uuid

sys.path.append(os.path.dirname(__file__))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from agent.inventory_agent import run_agent
from agent.finance_agent import run_finance_agent
from agent.sales_agent import run_sales_agent

app = FastAPI(title="Oga Assistant — SME Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Server-side session stores — one per agent
inventory_sessions: dict = {}
finance_sessions:   dict = {}
sales_sessions:     dict = {}

frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend')
app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(frontend_path, "index.html"))


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""


class ChatResponse(BaseModel):
    response: str
    session_id: str


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    history = inventory_sessions.get(session_id, [])
    result = run_agent(request.message, history)
    inventory_sessions[session_id] = result["updated_history"]
    return ChatResponse(response=result["response"], session_id=session_id)


@app.post("/finance", response_model=ChatResponse)
def finance(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    history = finance_sessions.get(session_id, [])
    result = run_finance_agent(request.message, history)
    finance_sessions[session_id] = result["updated_history"]
    return ChatResponse(response=result["response"], session_id=session_id)


@app.post("/sales", response_model=ChatResponse)
def sales(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    history = sales_sessions.get(session_id, [])
    result = run_sales_agent(request.message, history)
    sales_sessions[session_id] = result["updated_history"]
    return ChatResponse(response=result["response"], session_id=session_id)


@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    inventory_sessions.pop(session_id, None)
    finance_sessions.pop(session_id, None)
    sales_sessions.pop(session_id, None)
    return {"cleared": session_id}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "inventory_sessions": len(inventory_sessions),
        "finance_sessions":   len(finance_sessions),
        "sales_sessions":     len(sales_sessions),
    }