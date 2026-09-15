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
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ingestion.config import get_settings, load_tenants_config, get_tenant, TenantConfig
from api.retriever import retrieve_tenant_chunks, TenantIsolationError, CollectionNotFoundError
from api.prompts import build_rag_prompt, format_sources_for_response, RAG_SYSTEM_PROMPT
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
        description="Unique identifier of the tenant (e.g., 'acme', 'globex').",
        examples=["acme"],
    )
    question: str = Field(
        ...,
        description="User question to be answered from the tenant document corpus.",
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


@app.get("/", tags=["System"])
async def root() -> Dict[str, Any]:
    """Root metadata endpoint."""
    return {
        "service": "Multi-Tenant RAG System API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "endpoints": {
            "query": "POST /query",
            "tenants": "GET /tenants",
            "health": "GET /health",
        },
    }


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
    3. Retrieve top-k chunks from tenant's dedicated Chroma collection.
    4. Build a grounded prompt with strict context-only instructions.
    5. Generate an answer via the configured LLM provider (Gemini by default).
    6. Return answer with source citations and chunk count.
    """
    clean_tenant_id = request.tenant_id.strip().lower()
    clean_question = request.question.strip()

    # --- Step 1 & 2: Input validation ---
    if not clean_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'question' field cannot be empty or only whitespace.",
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
        answer = llm.generate_answer(
            prompt=prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
            temperature=0.0,
        )
        logger.info(
            f"Generated answer for tenant '{clean_tenant_id}' via '{llm.provider_name}/{llm.model_name}'."
        )
    except Exception as exc:
        logger.error(f"LLM generation failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Answer generation failed: {str(exc)}",
        )

    # --- Step 6: Format sources and return response ---
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
