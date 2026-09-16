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
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Validation constraints
MAX_QUESTION_LENGTH: int = 1000

from ingestion.config import (
    get_settings,
    load_tenants_config,
    get_tenant,
    TenantConfig,
    PROJECT_ROOT,
)
from api.retriever import retrieve_tenant_chunks, TenantIsolationError, CollectionNotFoundError
from api.prompts import build_rag_prompt, format_sources_for_response, RAG_SYSTEM_PROMPT, clean_rag_response
from api.llm_provider import get_llm_adapter

# Setup logger
logger = logging.getLogger("api.main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
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

# Serve frontend assets (avatars, etc.) from /static/
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Format Pydantic / schema validation failures into clear, human-readable error messages."""
    errors: List[str] = []
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
            errors.append("Invalid JSON syntax in request body")
        else:
            errors.append(f"Invalid value for field '{field_name}': {msg}")

    summary = "; ".join(errors) if errors else "Malformed request payload."
    detail_message = f"Malformed request: {summary}"
    logger.warning(f"Rejected malformed request on {request.url.path}: {detail_message}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
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
            "chat": "GET /chat",
            "query": "POST /query",
            "tenants": "GET /tenants",
            "health": "GET /health",
            "documents": "GET /documents/{filename}",
        },
    }


@app.get("/chat", tags=["Testing"])
async def testing_chat_ui():
    """Serve the interactive testing chat console web page."""
    frontend_path = PROJECT_ROOT / "frontend" / "index.html"
    if not frontend_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Testing frontend index.html not found.",
        )
    return FileResponse(str(frontend_path), media_type="text/html")


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
            detail=f"Configuration error: {str(exc)}",
        )


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
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Query"],
    responses={
        400: {
            "description": "Unknown or invalid tenant ID, or empty query question.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Unknown tenant 'unknown_corp'. Available configured tenants: [acme, globex]"
                    }
                }
            },
        },
        500: {
            "description": "Internal error during retrieval or generation.",
        },
    },
)
async def query_tenant(request: QueryRequest) -> QueryResponse:
    """Full RAG pipeline: retrieve → prompt → generate → respond.

    Steps:
    1. Validate tenant_id against tenants.yaml (400 if unknown).
    2. Validate question is non-empty (400 if blank).
    3. Check for generic small talk (bypasses retrieval/LLM if matched).
    4. Retrieve top-k chunks from tenant's dedicated Chroma collection.
    5. Build a grounded prompt with strict context-only instructions.
    6. Generate an answer via the configured LLM provider (Gemini by default).
    7. Return answer with source citations and chunk count.
    """
    clean_tenant_id = request.tenant_id.strip().lower()
    clean_question = request.question.strip()

    # --- Step 1: Validate tenant_id ---
    if not clean_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'tenant_id' field cannot be empty or only whitespace.",
        )

    # --- Step 2: Validate question (non-empty & length bounds) ---
    if not clean_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'question' field cannot be empty or only whitespace.",
        )

    if len(clean_question) > MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"The 'question' field exceeds maximum allowed length of "
                f"{MAX_QUESTION_LENGTH} characters (received {len(clean_question)} characters)."
            ),
        )

    try:
        tenant_config: TenantConfig = get_tenant(clean_tenant_id)
    except ValueError as exc:
        logger.warning(f"Rejected query for invalid tenant '{request.tenant_id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
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
            top_k=request.top_k,
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
    return QueryResponse(
        tenant_id=tenant_config.id,
        tenant_name=tenant_config.name,
        question=clean_question,
        answer=answer,
        sources=[],
        chunks_retrieved=len(chunks),
        message=f"Answer generated from {len(chunks)} document chunk(s) for {tenant_config.name} via {llm.provider_name}.",
    )
