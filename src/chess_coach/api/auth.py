"""JWT authentication for Chess Coach API."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt

from ..config import settings
from .schemas import TokenRequest, TokenResponse

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

http_bearer = HTTPBearer()

router = APIRouter(tags=["auth"])


def _encode(password: str) -> bytes:
    """Encode password to UTF-8 and truncate to bcrypt's 72-byte limit."""
    return password.encode("utf-8")[:72]


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    return _bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))


def hash_password(password: str) -> str:
    """Return bcrypt hash of *password*."""
    return _bcrypt.hashpw(_encode(password), _bcrypt.gensalt()).decode("utf-8")


def create_access_token(username: str) -> str:
    """Create a JWT access token valid for ACCESS_TOKEN_EXPIRE_DAYS days."""
    expire = datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, settings.api_secret_key, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
) -> str:
    """
    FastAPI dependency — validates the Bearer JWT and returns the username.
    Raises 401 if the token is missing, expired, or tampered with.
    """
    if not settings.api_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API auth not configured. Run 'chess-coach api-setup' first.",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.api_secret_key,
            algorithms=[ALGORITHM],
        )
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return username
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/auth/token", response_model=TokenResponse)
async def login(request: TokenRequest) -> TokenResponse:
    """
    Exchange username + password for a 30-day JWT access token.

    Use the returned token as `Authorization: Bearer <token>` on all other endpoints.
    """
    if not settings.api_secret_key or not settings.api_password_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API auth not configured. Run 'chess-coach api-setup' first.",
        )

    if request.username != settings.api_username:
        logger.warning(f"auth: LOGIN FAILED — unknown username '{request.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(request.password, settings.api_password_hash):
        logger.warning(f"auth: LOGIN FAILED — wrong password for user '{request.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(request.username)
    logger.info(f"Issued token for user '{request.username}'")
    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_DAYS * 86400,
    )
