import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr
from typing import Optional

from database.models import get_connection
from auth.utils import hash_password, verify_password, create_access_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request models ────────────────────────────────────────────────────────────
class SignupRequest(BaseModel):
    business_name: str
    business_type: Optional[str] = "provisions"
    full_name:     str
    email:         str
    password:      str


class LoginRequest(BaseModel):
    email:    str
    password: str


# ── Signup ────────────────────────────────────────────────────────────────────
@router.post("/signup", status_code=201)
def signup(request: SignupRequest):
    """
    Creates a new business and owner account.
    Returns a JWT token so the user is immediately logged in.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if email is already registered
    cursor.execute("SELECT id FROM users WHERE email = ?", (request.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered.")

    # Create the business first
    cursor.execute("""
        INSERT INTO businesses (name, email, business_type)
        VALUES (?, ?, ?)
    """, (request.business_name, request.email, request.business_type))
    business_id = cursor.lastrowid

    # Create the owner user account
    password_hash = hash_password(request.password)
    cursor.execute("""
        INSERT INTO users (business_id, full_name, email, password_hash, role)
        VALUES (?, ?, ?, ?, 'owner')
    """, (business_id, request.full_name, request.email, password_hash))
    user_id = cursor.lastrowid

    conn.commit()
    conn.close()

    # Create and return a token so they're logged in immediately
    token = create_access_token(user_id, business_id, request.email)

    return {
        "token":         token,
        "user_id":       user_id,
        "business_id":   business_id,
        "full_name":     request.full_name,
        "business_name": request.business_name,
        "business_type": request.business_type,
    }


# ── Login ─────────────────────────────────────────────────────────────────────
@router.post("/login")
def login(request: LoginRequest):
    """
    Verifies email and password.
    Returns a JWT token if credentials are correct.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Find the user by email
    cursor.execute("""
        SELECT u.id, u.business_id, u.full_name, u.password_hash,
               b.name AS business_name, b.business_type
        FROM users u
        JOIN businesses b ON b.id = u.business_id
        WHERE u.email = ?
    """, (request.email,))

    user = cursor.fetchone()
    conn.close()

    # Never reveal whether email or password was wrong —
    # just say "invalid credentials" for security
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user = dict(user)

    if not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(user["id"], user["business_id"], request.email)

    return {
        "token":         token,
        "user_id":       user["id"],
        "business_id":   user["business_id"],
        "full_name":     user["full_name"],
        "business_name": user["business_name"],
        "business_type": user["business_type"],
    }


# ── Get current user (verify token) ──────────────────────────────────────────
@router.get("/me")
def get_me(authorization: Optional[str] = Header(None)):
    """
    Returns the current user's info from their token.
    Used by the frontend to check if the user is still logged in.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated.")

    token = authorization.replace("Bearer ", "")
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.full_name, u.email, u.role,
               b.name AS business_name, b.business_type
        FROM users u
        JOIN businesses b ON b.id = u.business_id
        WHERE u.id = ?
    """, (payload["user_id"],))

    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return dict(user)