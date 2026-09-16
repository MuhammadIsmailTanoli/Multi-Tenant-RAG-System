"""Authentication and tenant-scoped JWT token management for Multi-Tenant RAG System.

Enforces cryptographic tenant boundary isolation:
1. Tenant company password verification using bcrypt hashing.
2. Creation of short-lived signed JWT access tokens strictly scoped to a specific tenant_id.
3. Strict token verification asserting matching tenant scope for all protected endpoints.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import logging
import bcrypt
import jwt
from fastapi import Header, HTTPException, status
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from ingestion.config import get_settings

logger = logging.getLogger("api.auth")


def verify_company_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Args:
        plain_password: The plaintext candidate password provided by the caller.
        hashed_password: The stored bcrypt hash string from tenants.yaml.

    Returns:
        True if password matches the hash, False otherwise.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception as exc:
        logger.warning(f"Error during password hash verification: {exc}")
        return False


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt and return the hash string.

    Args:
        plain_password: The plaintext password to hash.

    Returns:
        UTF-8 encoded bcrypt hash string.
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def create_tenant_token(
    tenant_id: str,
    google_sub: Optional[str] = None,
    email: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate a signed JWT access token scoped to tenant_id and tied to google_sub.

    Args:
        tenant_id: Unique identifier of the tenant.
        google_sub: Optional stable Google user ID (sub claim).
        email: Optional verified user email address.
        expires_delta: Optional custom token expiration duration.

    Returns:
        Encoded signed JWT string containing tenant_id and google_sub.
    """
    settings = get_settings()
    clean_tenant_id = tenant_id.strip().lower()

    if expires_delta is not None:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_expiration_minutes
        )

    payload: Dict[str, Any] = {
        "sub": clean_tenant_id,
        "tenant_id": clean_tenant_id,
        "google_sub": str(google_sub) if google_sub else "",
        "email": email or "",
        "iat": datetime.now(timezone.utc),
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_tenant_token(token: str) -> Dict[str, Any]:
    """Decode and validate a tenant-scoped JWT access token.

    Args:
        token: Raw JWT string.

    Returns:
        Decoded payload dictionary.

    Raises:
        HTTPException 401 if token is expired, invalid, or malformed.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Rejected expired JWT access token.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Authorization token has expired. Please re-authenticate via POST /auth/company.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as exc:
        logger.warning(f"Rejected invalid JWT access token: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: Invalid authorization token ({str(exc)}).",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_tenant(authorization: Optional[str] = Header(None)) -> str:
    """FastAPI dependency to extract and verify the tenant_id from the Bearer token.

    Args:
        authorization: 'Authorization' HTTP header value (e.g., 'Bearer <token>').

    Returns:
        Validated tenant_id embedded in the signed token.

    Raises:
        HTTPException 401 if header is missing, malformed, or invalid.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Missing Authorization header. Expected format: 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Malformed Authorization header. Expected format: 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Bearer token is empty.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_tenant_token(token)
    token_tenant = payload.get("tenant_id")
    if not token_tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Token payload missing 'tenant_id'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return str(token_tenant).strip().lower()


def verify_google_id_token(
    token: str,
    client_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify a Google OAuth 2.0 ID token server-side and extract the claims.

    Args:
        token: Raw Google ID token JWT string from the frontend.
        client_id: Optional Google Client ID to verify audience (aud claim).

    Returns:
        Dict containing decoded Google token claims (including 'sub', 'email', etc.).

    Raises:
        HTTPException 401 if token is invalid, expired, or verification fails.
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Google ID token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    expected_client_id = client_id or settings.google_client_id

    try:
        request = google_requests.Request()
        id_info = google_id_token.verify_oauth2_token(
            token.strip(),
            request,
            expected_client_id,
        )
        return id_info
    except ValueError as exc:
        logger.warning(f"Google ID token verification failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: Invalid or expired Google ID token ({str(exc)}).",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as exc:
        logger.error(f"Unexpected error during Google ID token verification: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: Unable to verify Google ID token ({str(exc)}).",
            headers={"WWW-Authenticate": "Bearer"},
        )


def verify_and_extract_google_identity(token: str) -> Dict[str, Any]:
    """Verify Google OAuth 2.0 ID token and ensure valid 'sub' and 'email' claims exist.

    Args:
        token: Raw Google ID token JWT string.

    Returns:
        Dict with decoded token claims (guaranteeing 'sub' and 'email').

    Raises:
        HTTPException 401 if token is invalid, expired, or missing required claims.
    """
    id_info = verify_google_id_token(token)
    sub = id_info.get("sub")
    email = id_info.get("email")

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Google ID token is missing required 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Google ID token is missing required 'email' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return id_info

