"""FastAPI application for the Multi-Tenant RAG System.

Exposes endpoints for querying tenant-isolated document collections,
validating tenant requests against tenants.yaml, and retrieving system health.
"""

from typing import Any, Dict, List, Optional
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ingestion.config import get_settings, load_tenants_config, get_tenant, TenantConfig

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

    model_config = {
        "json_schema_extra": {
            "example": {
                "tenant_id": "acme",
                "question": "What is the policy on equipment usage?",
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
        }
    },
)
async def query_tenant(request: QueryRequest) -> QueryResponse:
    """Accept a user query alongside tenant identification.

    Strictly validates the tenant_id against tenants.yaml:
    - If tenant_id is unknown or invalid -> returns HTTP 400 Bad Request
    - If question is empty or whitespace -> returns HTTP 400 Bad Request
    - If tenant is valid -> returns validated response
    """
    clean_tenant_id = request.tenant_id.strip().lower()
    clean_question = request.question.strip()

    if not clean_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'question' field cannot be empty or only whitespace.",
        )

    # Validate tenant against tenants.yaml
    try:
        tenant_config: TenantConfig = get_tenant(clean_tenant_id)
    except ValueError as exc:
        # get_tenant raises ValueError for unknown tenant IDs
        logger.warning(f"Rejected query for invalid tenant '{request.tenant_id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    logger.info(
        f"Valid query accepted for tenant '{tenant_config.id}' ({tenant_config.name}): "
        f"'{clean_question}'"
    )

    return QueryResponse(
        tenant_id=tenant_config.id,
        tenant_name=tenant_config.name,
        question=clean_question,
        answer=None,
        sources=[],
        message=f"Tenant '{tenant_config.name}' validated. Ready for context retrieval.",
    )
