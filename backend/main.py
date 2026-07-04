import sys
import os
import uuid

from database.models import create_tables
from auth.models import create_auth_tables, create_default_business

sys.path.append(os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from agent.inventory_agent import run_agent
from agent.finance_agent import run_finance_agent
from agent.sales_agent import run_sales_agent
from agent.orchestrator import run_orchestrator
from database.crud import (
    get_all_products, get_product_by_id,
    create_product, update_product, delete_product,
)
from auth.routes import router as auth_router
from auth.utils import decode_token

app = FastAPI(title="Oga Assistant — SME Agent")

# Create database tables on startup if they don't exist
create_tables()
create_auth_tables()
create_default_business()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

inventory_sessions:    dict = {}
finance_sessions:      dict = {}
sales_sessions:        dict = {}
orchestrator_sessions: dict = {}

frontend_path = os.path.join(os.path.dirname(__file__), '..', 'frontend')
app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
def serve_landing():
    return FileResponse(os.path.join(frontend_path, "landing.html"))

@app.get("/app")
def serve_frontend():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/admin")
def serve_admin():
    return FileResponse(os.path.join(frontend_path, "admin.html"))

@app.get("/pos")
def serve_pos():
    return FileResponse(os.path.join(frontend_path, "pos.html"))

@app.get("/login")
def serve_login():
    return FileResponse(os.path.join(frontend_path, "login.html"))


app.include_router(auth_router)
from pos import router as pos_router
app.include_router(pos_router)


# ── Token verification — returns business_id ──────────────────────────────────
def get_business_id(authorization: Optional[str]) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")
    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return payload["business_id"]


# ── Request / Response models ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:    str
    session_id: str = ""


class ChatResponse(BaseModel):
    response:   str
    session_id: str


class ProductPayload(BaseModel):
    name:              str
    category:          Optional[str]   = None
    unit:              Optional[str]   = None
    current_stock:     Optional[float] = 0
    reorder_threshold: Optional[float] = 10
    reorder_quantity:  Optional[float] = 50
    unit_cost:         Optional[float] = 0
    selling_price:     Optional[float] = 0


# ── Agent endpoints ───────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    session_id  = request.session_id or str(uuid.uuid4())
    history     = inventory_sessions.get(session_id, [])
    result      = run_agent(request.message, history, business_id)
    inventory_sessions[session_id] = result["updated_history"]
    return ChatResponse(response=result["response"], session_id=session_id)


@app.post("/finance", response_model=ChatResponse)
def finance(request: ChatRequest, authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    session_id  = request.session_id or str(uuid.uuid4())
    history     = finance_sessions.get(session_id, [])
    result      = run_finance_agent(request.message, history, business_id)
    finance_sessions[session_id] = result["updated_history"]
    return ChatResponse(response=result["response"], session_id=session_id)


@app.post("/sales", response_model=ChatResponse)
def sales(request: ChatRequest, authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    session_id  = request.session_id or str(uuid.uuid4())
    history     = sales_sessions.get(session_id, [])
    result      = run_sales_agent(request.message, history, business_id)
    sales_sessions[session_id] = result["updated_history"]
    return ChatResponse(response=result["response"], session_id=session_id)


@app.post("/orchestrator", response_model=ChatResponse)
def orchestrator(request: ChatRequest, authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    session_id  = request.session_id or str(uuid.uuid4())
    history     = orchestrator_sessions.get(session_id, [])
    result      = run_orchestrator(request.message, history, business_id)
    orchestrator_sessions[session_id] = result["updated_history"]
    return ChatResponse(response=result["response"], session_id=session_id)


@app.delete("/session/{session_id}")
def clear_session(session_id: str, authorization: Optional[str] = Header(None)):
    get_business_id(authorization)
    inventory_sessions.pop(session_id, None)
    finance_sessions.pop(session_id, None)
    sales_sessions.pop(session_id, None)
    orchestrator_sessions.pop(session_id, None)
    return {"cleared": session_id}


# ── Product endpoints ─────────────────────────────────────────────────────────
@app.get("/products")
def list_products(authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    return get_all_products(business_id)


@app.get("/products/{product_id}")
def get_product(product_id: int, authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    product = get_product_by_id(product_id, business_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post("/products", status_code=201)
def add_product(payload: ProductPayload,
                authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    data = payload.model_dump()
    return create_product(data, business_id)


@app.put("/products/{product_id}")
def edit_product(product_id: int, payload: ProductPayload,
                 authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    existing = get_product_by_id(product_id, business_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return update_product(product_id, data, business_id)


@app.delete("/products/{product_id}")
def remove_product(product_id: int,
                   authorization: Optional[str] = Header(None)):
    business_id = get_business_id(authorization)
    existing = get_product_by_id(product_id, business_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")
    success = delete_product(product_id, business_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete product")
    return {"deleted": True, "product_id": product_id}


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "inventory_sessions":    len(inventory_sessions),
        "finance_sessions":      len(finance_sessions),
        "sales_sessions":        len(sales_sessions),
        "orchestrator_sessions": len(orchestrator_sessions),
    }