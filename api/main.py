"""FastAPI application for the Multi-Tenant RAG System.

Exposes endpoints for querying tenant-isolated document collections,
validating tenant requests against tenants.yaml, and retrieving system health.

Full RAG pipeline on POST /query:
  1. Validate tenant_id against tenants.yaml
  2. Retrieve top-k chunks from tenant's isolated Chroma collection
  3. Build a grounded prompt with strict context-only instructions
  4. Generate an answer via the configured LLM provider (Gemini by default)
  5. Return the answer with source citations
"""

from typing import Any, Dict, List, Optional
import logging
import re
import unicodedata
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

# Validation constraints
MAX_QUESTION_LENGTH: int = 500

from ingestion.config import (
    get_settings,
    load_tenants_config,
    list_tenants,
    get_tenant,
    TenantConfig,
    PROJECT_ROOT,
)
from api.retriever import retrieve_tenant_chunks, TenantIsolationError, CollectionNotFoundError
from api.prompts import build_rag_prompt, format_sources_for_response, RAG_SYSTEM_PROMPT, clean_rag_response
from api.llm_provider import get_llm_adapter
from api.auth import (
    verify_company_password,
    create_tenant_token,
    decode_tenant_token,
    get_token_tenant,
    verify_google_id_token,
    verify_and_extract_google_identity,
)
from api.rate_limiter import (
    limiter,
    rate_limit_exceeded_handler,
    RateLimitExceeded,
    get_user_limits_status,
)

# Setup logger
logger = logging.getLogger("api.main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


class CompanyAuthRequest(BaseModel):
    """Request payload for tenant company authentication requiring prior Google identity verification."""

    tenant_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier of the tenant (e.g., 'acme', 'globex').",
        examples=["acme"],
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Company password for the tenant.",
        examples=["AcmeSecret2026!"],
    )
    google_id_token: str = Field(
        ...,
        min_length=10,
        description="Valid Google OAuth 2.0 ID token of the user.",
        examples=["eyJhbGciOiJSUzI1NiIsImtpZCI6Ij..."],
    )


class CompanyAuthResponse(BaseModel):
    """Response payload for successful company authentication with unified session token."""

    access_token: str = Field(..., description="Signed combined JWT access token scoped to tenant and Google user.")
    token_type: str = Field(default="bearer", description="Token type header standard.")
    tenant_id: str = Field(..., description="Tenant identifier to which token is scoped.")
    google_sub: str = Field(..., description="Verified Google user ID (sub claim) bound to this session.")
    email: Optional[str] = Field(default=None, description="Verified Google user email bound to this session.")
    expires_in: int = Field(..., description="Token lifespan in seconds.")
    message: str = Field(
        default="Authentication successful.",
        description="Status message.",
    )


class SwitchCompanyRequest(BaseModel):
    """Request payload for switching company access using an existing Google identity token."""

    new_tenant_id: str = Field(
        ...,
        min_length=1,
        description="Target tenant identifier to switch to (e.g., 'acme', 'globex').",
        examples=["globex"],
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Company password for the target tenant.",
        examples=["GlobexSecret2026!"],
    )
    google_id_token: str = Field(
        ...,
        min_length=10,
        description="Valid Google OAuth 2.0 ID token still held client-side.",
        examples=["eyJhbGciOiJSUzI1NiIsImtpZCI6Ij..."],
    )


class GoogleAuthRequest(BaseModel):
    """Request payload for verifying a Google Sign-In OAuth2 ID token."""

    id_token: str = Field(
        ...,
        min_length=10,
        description="Google OAuth2 ID token JWT string received from Google Sign-In.",
        examples=["eyJhbGciOiJSUzI1NiIsImtpZCI6Ij..."],
    )


class GoogleAuthResponse(BaseModel):
    """Response payload with extracted Google user profile claims."""

    google_user_id: str = Field(..., description="Stable unique Google user ID (sub claim).")
    email: str = Field(..., description="User's verified Google email address.")
    email_verified: bool = Field(default=False, description="Whether email address is verified by Google.")
    name: Optional[str] = Field(default=None, description="User's full name from Google profile.")
    picture: Optional[str] = Field(default=None, description="URL to user's Google profile picture.")
    message: str = Field(
        default="Google authentication successful.",
        description="Status message.",
    )


class QueryRequest(BaseModel):
    """Incoming query request payload."""

    tenant_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier of the tenant (e.g., 'acme', 'globex').",
        examples=["acme"],
    )
    question: str = Field(
        ...,
        min_length=1,
        max_length=MAX_QUESTION_LENGTH,
        description=f"User question to be answered from the tenant document corpus (1-{MAX_QUESTION_LENGTH} characters).",
        examples=["What is the probationary period duration?"],
    )
    top_k: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Number of document chunks to retrieve for context (1-10).",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "tenant_id": "acme",
                "question": "What is the policy on equipment usage?",
                "top_k": 4,
            }
        }
    }


class QueryResponse(BaseModel):
    """Query response payload."""

    tenant_id: str = Field(..., description="Validated tenant identifier.")
    tenant_name: str = Field(..., description="Organization display name.")
    question: str = Field(..., description="User query submitted.")
    answer: Optional[str] = Field(
        default=None,
        description="Synthesized answer grounded strictly in tenant context.",
    )
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of cited source chunks supporting the answer.",
    )
    chunks_retrieved: int = Field(
        default=0,
        description="Number of context chunks used for generation.",
    )
    message: str = Field(
        default="Query accepted and validated for tenant.",
        description="Status message or execution feedback.",
    )


class TenantSummary(BaseModel):
    """Summary representation of a registered tenant."""

    id: str
    name: str
    collection_name: str
    description: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown routines."""
    settings = get_settings()
    logger.info("Initializing Multi-Tenant RAG API...")
    try:
        tenants = load_tenants_config()
        logger.info(f"Loaded {len(tenants)} active tenants: {list(tenants.keys())}")
    except Exception as exc:
        logger.warning(f"Could not load tenants configuration on startup: {exc}")
    yield
    logger.info("Shutting down Multi-Tenant RAG API.")


app = FastAPI(
    title="Multi-Tenant RAG API",
    description=(
        "Production-grade Multi-Tenant RAG backend with strict physical vector collection "
        "segregation, preventing cross-tenant document contamination."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Attach SlowAPI rate limiter and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Enable CORS for local development and web frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve source tenant handbook PDFs statically from /documents/{filename}
HANDBOOKS_DIR = PROJECT_ROOT / "data" / "handbooks"
HANDBOOKS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/documents", StaticFiles(directory=str(HANDBOOKS_DIR)), name="documents")

# Serve Vite production build assets (JS, CSS) from /assets/
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
if FRONTEND_DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="assets")

# Serve legacy frontend directory for avatars/images from /static/
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


def check_control_characters(text: str, field_name: str = "question") -> Optional[str]:
    """Check for disallowed control characters in the input text.

    Allows standard formatting whitespace: newline (\n), carriage return (\r), tab (\t).
    Disallows null bytes, backspaces, escapes, and all other unprintable control codes.

    Returns error description if a control character is detected, else None.
    """
    for idx, ch in enumerate(text):
        if ch in ("\n", "\r", "\t"):
            continue
        code = ord(ch)
        category = unicodedata.category(ch)
        if category == "Cc" or code < 32 or code == 127:
            char_repr = repr(ch)
            return (
                f"Validation failed: '{field_name}' contains invalid or unprintable "
                f"control character {char_repr} (code {code}) at character index {idx}."
            )
    return None


@app.middleware("http")
async def payload_validation_middleware(request: Request, call_next):
    """Validate incoming request payloads: reject binary content types and non-UTF-8 bytes."""
    if request.method in ("POST", "PUT", "PATCH") and request.url.path == "/query":
        content_type = request.headers.get("content-type", "").lower()

        # 1. Reject binary content types
        if any(b in content_type for b in ("octet-stream", "binary", "x-binary", "application/x-zip")):
            logger.warning(f"Rejected binary Content-Type '{content_type}' on {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={
                    "detail": "Validation failed: Binary payloads are not supported. Content-Type must be 'application/json' with UTF-8 encoding."
                },
            )

        # 2. Check raw body for non-UTF-8 binary byte sequences
        try:
            raw_body = await request.body()
            if raw_body:
                raw_body.decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.warning(f"Rejected non-UTF-8 payload on {request.url.path}: {exc}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={
                    "detail": f"Validation failed: Payload is not valid UTF-8. Non-UTF-8 or binary byte sequences detected: {str(exc)}."
                },
            )

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Format Pydantic / schema validation failures into clear, human-readable error messages."""
    errors: List[str] = []
    has_json_syntax_error = False

    for err in exc.errors():
        loc_parts = [str(part) for part in err.get("loc", []) if part != "body"]
        field_name = ".".join(loc_parts) if loc_parts else "body"
        msg = err.get("msg", "Invalid value")
        err_type = err.get("type", "")

        if err_type == "missing":
            errors.append(f"Missing required field '{field_name}'")
        elif "string_too_long" in err_type:
            errors.append(
                f"The '{field_name}' field exceeds maximum allowed length of {MAX_QUESTION_LENGTH} characters"
            )
        elif "string_too_short" in err_type:
            errors.append(f"The '{field_name}' field cannot be empty")
        elif err_type == "json_invalid":
            has_json_syntax_error = True
            errors.append("Invalid JSON syntax in request body")
        else:
            errors.append(f"Invalid value for field '{field_name}': {msg}")

    summary = "; ".join(errors) if errors else "Malformed request payload."
    detail_message = f"Validation failed: Malformed request - {summary}"
    logger.warning(f"Rejected invalid request on {request.url.path}: {detail_message}")

    status_code = (
        status.HTTP_400_BAD_REQUEST
        if has_json_syntax_error
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail_message,
            "errors": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled server exceptions to prevent exposing internal stack traces or paths."""
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )
    logger.exception(f"Unhandled exception during {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred while processing the request."},
    )


@app.get("/", tags=["System"])
async def root() -> Dict[str, Any]:
    """Root metadata endpoint."""
    return {
        "service": "Multi-Tenant RAG System API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "test_console_url": "/chat",
        "endpoints": {
            "auth": "POST /auth/company",
            "switch_company": "POST /auth/switch-company",
            "google_auth": "POST /auth/google",
            "chat": "GET /chat",
            "query": "POST /query",
            "tenants": "GET /tenants",
            "health": "GET /health",
            "documents": "GET /documents/{filename}",
            "limits": "GET /limits",
        },
    }


@app.get("/chat", tags=["Frontend"])
async def serve_chat_app():
    """Serve the React/Vite multi-tenant RAG chat application.

    Looks first for the production Vite dist build; falls back to legacy index.html.
    """
    # Prefer Vite production build
    vite_index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if vite_index.exists():
        return FileResponse(str(vite_index), media_type="text/html")

    # Fallback to legacy plain HTML file if dist not yet built
    legacy_index = PROJECT_ROOT / "frontend" / "index.html"
    if legacy_index.exists():
        return FileResponse(str(legacy_index), media_type="text/html")

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Frontend not found. Run 'npm run build' inside the frontend/ directory first.",
    )


@app.get("/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint validating tenant configuration availability."""
    try:
        tenants = load_tenants_config()
        return {
            "status": "healthy",
            "active_tenants_count": len(tenants),
            "tenants": list(tenants.keys()),
        }
    except Exception as exc:
        logger.error(f"Health check failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {str(exc)}",
        )


@app.get("/limits", tags=["System"])
async def get_limits_status(request: Request) -> Dict[str, Any]:
    """Return the current user's daily and weekly query usage, remaining quotas, and reset times."""
    auth_header = request.headers.get("Authorization", "")
    google_sub = None
    email = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        try:
            payload = decode_tenant_token(token)
            google_sub = payload.get("google_sub")
            email = payload.get("email")
        except Exception as e:
            logger.debug(f"Could not extract token claims for /limits: {e}")

    status_data = get_user_limits_status(google_sub)
    status_data["email"] = email
    return status_data


@app.get("/tenants", response_model=List[TenantSummary], tags=["Tenants"])
async def list_registered_tenants() -> List[TenantSummary]:
    """List all registered tenants and their collection parameters."""
    try:
        tenants = load_tenants_config()
        return [
            TenantSummary(
                id=t.id,
                name=t.name,
                collection_name=t.collection_name,
                description=t.description,
            )
            for t in tenants.values()
        ]
    except Exception as exc:
        logger.error(f"Failed to fetch tenants: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to load tenants: {str(exc)}",
        )


# ---------------------------------------------------------------------------
# Small-Talk Interceptor (bypasses vector store and LLM context calls)
# ---------------------------------------------------------------------------
SMALL_TALK_PATTERNS = [
    # Greetings: hi, hello, hey, etc.
    (
        re.compile(
            r"^(hi|hello|hey|heyy+|howdy|greetings|hi\s+there|hello\s+there|good\s+(morning|afternoon|evening))$",
            re.IGNORECASE,
        ),
        lambda name: f"Hello! I am the AI assistant for {name}. How can I help you today?",
    ),
    # How are you: how are you, how's it going, etc.
    (
        re.compile(
            r"^(how\s+are\s+you(\s+doing)?|hows\s+it\s+going|how\s+do\s+you\s+do|whats\s+up)$",
            re.IGNORECASE,
        ),
        lambda name: f"I'm doing well, thank you! How can I assist you with {name}'s documents today?",
    ),
    # Who are you / Identity
    (
        re.compile(
            r"^(who\s+are\s+you|what\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do|tell\s+me\s+about\s+yourself)$",
            re.IGNORECASE,
        ),
        lambda name: f"I am the knowledge assistant for {name}. I can help answer questions about company policies, guidelines, and handbooks.",
    ),
    # Thanks / Gratitude
    (
        re.compile(
            r"^(thanks|thank\s+you|thank\s+you\s+very\s+much|thanks\s+a\s+lot|thx|many\s+thanks)$",
            re.IGNORECASE,
        ),
        lambda name: "You're welcome! Let me know if you need any further assistance.",
    ),
    # Bye / Farewell
    (
        re.compile(
            r"^(bye|goodbye|bye\s+bye|see\s+you|see\s+ya|cya|farewell|have\s+a\s+good\s+(day|one))$",
            re.IGNORECASE,
        ),
        lambda name: "Goodbye! Have a great day!",
    ),
]


def get_small_talk_reply(question: str, tenant_name: str) -> Optional[str]:
    """Return a direct friendly reply for small-talk queries, skipping database retrieval.

    Args:
        question: Cleaned user query.
        tenant_name: Display name of the active tenant.

    Returns:
        Friendly response string if question matches small talk, otherwise None.
    """
    normalized = re.sub(r"[^\w\s]", "", question).strip()
    if not normalized:
        return None

    for pattern, reply_fn in SMALL_TALK_PATTERNS:
        if pattern.match(normalized):
            return reply_fn(tenant_name)

    return None


@app.post(
    "/auth/company",
    response_model=CompanyAuthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
    responses={
        401: {
            "description": "Authentication failed: Invalid tenant ID or password.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Authentication failed: Invalid tenant ID or password."
                    }
                }
            },
        },
        422: {
            "description": "Validation failed: Malformed input payload.",
        },
    },
)
async def authenticate_company(req: CompanyAuthRequest) -> CompanyAuthResponse:
    """Authenticate a tenant company requiring prior Google identity verification, issuing a unified JWT."""
    # 1. Verify Google identity token - company session can only be issued to an already Google-verified user
    google_user = await run_in_threadpool(verify_and_extract_google_identity, req.google_id_token)
    google_sub = str(google_user["sub"])
    email = google_user.get("email")

    # 2. Validate tenant ID
    clean_tenant_id = req.tenant_id.strip().lower()
    try:
        tenant_config = get_tenant(clean_tenant_id)
    except ValueError:
        logger.warning(f"Failed authentication attempt for unknown tenant: '{req.tenant_id}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Invalid tenant ID or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Verify company password
    if not verify_company_password(req.password, tenant_config.password_hash):
        logger.warning(f"Failed authentication attempt for tenant '{clean_tenant_id}': Incorrect password.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Invalid tenant ID or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Issue combined JWT containing both tenant_id and google_sub
    settings = get_settings()
    token = create_tenant_token(clean_tenant_id, google_sub=google_sub, email=email)
    logger.info(
        f"Successfully authenticated company and generated combined JWT for tenant '{clean_tenant_id}' "
        f"and Google user '{email}' (sub: '{google_sub}')."
    )
    return CompanyAuthResponse(
        access_token=token,
        token_type="bearer",
        tenant_id=clean_tenant_id,
        google_sub=google_sub,
        email=email,
        expires_in=settings.jwt_expiration_minutes * 60,
        message=f"Successfully authenticated as {tenant_config.name} for {email}.",
    )


@app.post(
    "/auth/switch-company",
    response_model=CompanyAuthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
    responses={
        401: {
            "description": "Authentication failed: Invalid Google token or company password.",
        },
        422: {
            "description": "Validation failed: Unknown tenant or malformed input payload.",
        },
    },
)
async def switch_company(req: SwitchCompanyRequest) -> CompanyAuthResponse:
    """Switch active tenant company using client-held Google ID token without repeated Google sign-in."""
    # 1. Verify Google identity token held client-side
    google_user = await run_in_threadpool(verify_and_extract_google_identity, req.google_id_token)
    google_sub = str(google_user["sub"])
    email = google_user.get("email")

    # 2. Validate target tenant ID
    clean_tenant_id = req.new_tenant_id.strip().lower()
    try:
        tenant_config = get_tenant(clean_tenant_id)
    except ValueError:
        logger.warning(f"Switch company failed: unknown tenant '{req.new_tenant_id}'")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Validation failed: Unknown tenant '{req.new_tenant_id}'. Available configured tenants: {list_tenants()}",
        )

    # 3. Verify new company's password
    if not verify_company_password(req.password, tenant_config.password_hash):
        logger.warning(f"Switch company failed for tenant '{clean_tenant_id}': Incorrect password.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Invalid company password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Issue combined JWT scoped to the new tenant_id and tied to google_sub
    settings = get_settings()
    token = create_tenant_token(clean_tenant_id, google_sub=google_sub, email=email)
    logger.info(
        f"Successfully switched company session to '{clean_tenant_id}' for Google user '{email}' (sub: '{google_sub}')."
    )

    return CompanyAuthResponse(
        access_token=token,
        token_type="bearer",
        tenant_id=clean_tenant_id,
        google_sub=google_sub,
        email=email,
        expires_in=settings.jwt_expiration_minutes * 60,
        message=f"Successfully switched company access to {tenant_config.name} for {email}.",
    )


@app.get(
    "/auth/google/config",
    tags=["Authentication"],
    summary="Get public Google OAuth Client ID configuration for the frontend.",
)
async def get_google_auth_config() -> Dict[str, Any]:
    """Return public Google OAuth Client ID for the web frontend."""
    settings = get_settings()
    client_id = settings.google_client_id or ""
    return {
        "client_id": client_id,
        "enabled": bool(client_id),
    }


@app.post(
    "/auth/google",
    response_model=GoogleAuthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Authentication"],
    responses={
        401: {
            "description": "Authentication failed: Invalid, expired, or tampered Google ID token.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Authentication failed: Invalid or expired Google ID token (Token expired)."
                    }
                }
            },
        },
        422: {
            "description": "Validation failed: Malformed or missing input payload.",
        },
    },
)
async def authenticate_google(req: GoogleAuthRequest) -> GoogleAuthResponse:
    """Verify Google OAuth 2.0 ID token server-side and extract the stable user ID (sub claim) and email."""
    token_str = req.id_token.strip()
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Validation failed: 'id_token' field cannot be empty or contain only whitespace.",
        )

    # Server-side cryptographic token verification via google.oauth2.id_token.verify_oauth2_token
    id_info = await run_in_threadpool(verify_google_id_token, token_str)

    sub = id_info.get("sub")
    email = id_info.get("email")

    if not sub:
        logger.warning("Google ID token verified but missing 'sub' claim.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Google ID token is missing required 'sub' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not email:
        logger.warning("Google ID token verified but missing 'email' claim.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Google ID token is missing required 'email' claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info(f"Successfully verified Google Sign-In for user '{email}' (sub: '{sub}').")

    return GoogleAuthResponse(
        google_user_id=str(sub),
        email=str(email),
        email_verified=bool(id_info.get("email_verified", False)),
        name=id_info.get("name"),
        picture=id_info.get("picture"),
        message=f"Google authentication successful for {email}.",
    )


@app.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Query"],
    responses={
        400: {
            "description": "Malformed JSON syntax in request body.",
        },
        401: {
            "description": "Authentication failed: Missing, invalid, or expired authorization token.",
        },
        403: {
            "description": "Access forbidden: Authorization token tenant does not match requested tenant_id.",
        },
        422: {
            "description": "Validation failed: Unknown tenant, empty question, control characters, or non-UTF-8/binary payload.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Validation failed: Unknown tenant 'unknown_corp'. Available configured tenants: ['acme', 'globex']"
                    }
                }
            },
        },
        429: {
            "description": "Rate limit exceeded: Daily or weekly query limit reached for this Google user across all companies.",
        },
        500: {
            "description": "Internal error during retrieval or generation.",
        },
    },
)
@limiter.limit(get_settings().rate_limit_query)
async def query_tenant(
    request: Request,
    query_req: QueryRequest,
    token_tenant_id: str = Depends(get_token_tenant),
) -> QueryResponse:
    """Full RAG pipeline: retrieve → prompt → generate → respond.

    Steps:
    1. Validate tenant_id against tenants.yaml (422 if unknown).
    2. Enforce tenant token scope: token_tenant_id must match request tenant_id (403 if mismatch).
    3. Validate question is non-empty (422 if blank).
    4. Check for generic small talk (bypasses retrieval/LLM if matched).
    5. Retrieve top-k chunks from tenant's dedicated Chroma collection.
    6. Build a grounded prompt with strict context-only instructions.
    7. Generate an answer via the configured LLM provider (Gemini by default).
    8. Return answer with source citations and chunk count.
    """
    raw_tenant_id = query_req.tenant_id
    raw_question = query_req.question

    # --- Step 1: Validate tenant_id strictly ---
    if raw_tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Validation failed: 'tenant_id' field is required and cannot be null.",
        )

    clean_tenant_id = raw_tenant_id.strip().lower()
    if not clean_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Validation failed: 'tenant_id' field cannot be empty or contain only whitespace.",
        )

    tenant_ctrl_err = check_control_characters(raw_tenant_id, field_name="tenant_id")
    if tenant_ctrl_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=tenant_ctrl_err,
        )

    try:
        tenant_config: TenantConfig = get_tenant(clean_tenant_id)
    except ValueError as exc:
        available_tenants = list_tenants()
        logger.warning(f"Rejected query for unknown tenant '{raw_tenant_id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Validation failed: Unknown tenant '{raw_tenant_id}'. Available configured tenants: {available_tenants}",
        )

    # --- Step 1b: Verify token tenant matches request tenant ---
    if token_tenant_id != clean_tenant_id:
        logger.warning(
            f"Cross-tenant query blocked: Token scoped to '{token_tenant_id}' attempted to access '{clean_tenant_id}'."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Access forbidden: Authorization token is scoped to tenant '{token_tenant_id}', "
                f"which does not match the requested tenant '{clean_tenant_id}'."
            ),
        )

    # --- Step 2: Validate question strictly ---
    if raw_question is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Validation failed: 'question' field is required and cannot be null.",
        )

    # Reject unprintable / control characters in question
    question_ctrl_err = check_control_characters(raw_question, field_name="question")
    if question_ctrl_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=question_ctrl_err,
        )

    clean_question = raw_question.strip()
    if not clean_question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Validation failed: 'question' field cannot be empty or contain only whitespace.",
        )

    if len(clean_question) > MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Validation failed: 'question' field exceeds maximum allowed length of "
                f"{MAX_QUESTION_LENGTH} characters (received {len(clean_question)} characters)."
            ),
        )

    logger.info(
        f"RAG query for tenant '{tenant_config.id}' ({tenant_config.name}): '{clean_question}'"
    )

    # --- Step 2b: Handle generic / small-talk queries without touching the database ---
    small_talk_reply = get_small_talk_reply(clean_question, tenant_config.name)
    if small_talk_reply:
        logger.info(
            f"Handled small-talk query for tenant '{tenant_config.id}' without database retrieval: '{clean_question}'"
        )
        return QueryResponse(
            tenant_id=tenant_config.id,
            tenant_name=tenant_config.name,
            question=clean_question,
            answer=small_talk_reply,
            sources=[],
            chunks_retrieved=0,
            message=f"Direct small-talk reply for {tenant_config.name} (retrieval skipped).",
        )

    # --- Step 3: Retrieve top-k chunks from tenant's isolated collection ---
    try:
        chunks = retrieve_tenant_chunks(
            tenant_id=clean_tenant_id,
            question=clean_question,
            top_k=query_req.top_k,
        )
    except CollectionNotFoundError as exc:
        logger.error(f"Collection not found for tenant '{clean_tenant_id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except TenantIsolationError as exc:
        logger.critical(f"ISOLATION BREACH detected: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A tenant isolation error occurred. Contact system administrator.",
        )
    except Exception as exc:
        logger.error(f"Retrieval failed for tenant '{clean_tenant_id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context retrieval failed: {str(exc)}",
        )

    logger.info(f"Retrieved {len(chunks)} chunks for tenant '{clean_tenant_id}'.")

    # --- Step 4: Build grounded RAG prompt ---
    prompt = build_rag_prompt(
        question=clean_question,
        chunks=chunks,
        tenant_name=tenant_config.name,
    )

    # --- Step 5: Generate answer via configured LLM provider ---
    try:
        llm = get_llm_adapter()
        raw_answer = llm.generate_answer(
            prompt=prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
            temperature=0.0,
        )
        answer = clean_rag_response(raw_answer)
        logger.info(
            f"Generated answer for tenant '{clean_tenant_id}' via '{llm.provider_name}/{llm.model_name}'."
        )
    except Exception as exc:
        logger.error(f"LLM generation failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Answer generation failed: {str(exc)}",
        )

    # --- Step 6: Return response ---
    sources = format_sources_for_response(chunks)
    return QueryResponse(
        tenant_id=tenant_config.id,
        tenant_name=tenant_config.name,
        question=clean_question,
        answer=answer,
        sources=sources,
        chunks_retrieved=len(chunks),
        message=f"Answer generated from {len(chunks)} document chunk(s) for {tenant_config.name} via {llm.provider_name}.",
    )
