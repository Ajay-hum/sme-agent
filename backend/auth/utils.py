import os
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

# ── Password hashing ──────────────────────────────────────────────────────────
# bcrypt is the industry standard for password hashing.
# It is intentionally slow to make brute force attacks impractical.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Converts a plain password into a bcrypt hash for safe storage."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Checks if a plain password matches a stored hash.
    Returns True if they match, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT tokens ────────────────────────────────────────────────────────────────
# The secret key signs the token. Anyone with this key can create valid tokens,
# so it must stay in .env and never be committed to git.
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production-to-a-long-random-string")
ALGORITHM  = "HS256"
TOKEN_EXPIRE_DAYS = 30  # Token valid for 30 days


def create_access_token(user_id: int, business_id: int, email: str) -> str:
    """
    Creates a JWT token containing the user's ID, business ID, and email.
    The token expires after TOKEN_EXPIRE_DAYS days.
    """
    payload = {
        "user_id":     user_id,
        "business_id": business_id,
        "email":       email,
        "exp":         datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """
    Decodes and verifies a JWT token.
    Returns the payload dict if valid, None if invalid or expired.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None