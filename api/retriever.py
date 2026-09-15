"""Tenant-scoped vector retrieval module for Multi-Tenant RAG System.

Enforces strict tenant isolation by:
1. Routing queries exclusively to the requesting tenant's dedicated Chroma collection.
2. Embedding the incoming question using Qwen3-Embedding-0.6B.
3. Querying top-k nearest chunks using cosine similarity.
4. Performing a zero-trust post-retrieval audit: asserting that every single returned chunk
   has metadata['tenant_id'] == requested tenant_id. Raises an exception if any breach occurs.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

import chromadb

from ingestion.config import (
    get_tenant,
    TenantConfig,
)
from ingestion.embedder import get_embedder, QwenEmbedder
from ingestion.ingest import get_chroma_client

logger = logging.getLogger("api.retriever")


class TenantIsolationError(RuntimeError):
    """Raised when a retrieved chunk violates tenant boundary isolation."""
    pass


class CollectionNotFoundError(RuntimeError):
    """Raised when the vector collection for a tenant does not exist."""
    pass


@dataclass
class RetrievedChunk:
    """Standardized data container for a retrieved document chunk."""

    chunk_id: str
    text: str
    tenant_id: str
    source_file: str
    page_start: int
    page_end: int
    chunk_index: int
    token_count: int
    page_number: int = 1
    distance: Optional[float] = None
    similarity: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        """Formatted citation reference."""
        pages = (
            f"p. {self.page_start}"
            if self.page_start == self.page_end
            else f"pp. {self.page_start}–{self.page_end}"
        )
        return f"[{self.source_file}, {pages}, Chunk #{self.chunk_index}]"


def retrieve_tenant_chunks(
    tenant_id: str,
    question: str,
    top_k: int = 4,
    client: Optional[chromadb.PersistentClient] = None,
    embedder: Optional[QwenEmbedder] = None,
) -> List[RetrievedChunk]:
    """Retrieve top-k relevant document chunks for a specific tenant.

    Guarantees strict multi-tenant isolation:
    - Resolves tenant configuration from tenants.yaml.
    - Connects ONLY to that tenant's dedicated Chroma collection.
    - Embeds the query with Qwen3-Embedding-0.6B.
    - Audits every returned chunk's `tenant_id` metadata against the requested tenant.
    - Raises `TenantIsolationError` if any foreign chunk is detected.

    Args:
        tenant_id: Unique identifier of the tenant (e.g., 'acme', 'globex').
        question: User query text.
        top_k: Number of most relevant chunks to retrieve.
        client: Optional Chroma persistent client (uses default if None).
        embedder: Optional embedding generator (uses Qwen3 singleton if None).

    Returns:
        List of verified, strictly isolated RetrievedChunk instances.

    Raises:
        ValueError: If tenant_id or question is invalid.
        CollectionNotFoundError: If tenant's vector collection does not exist or is empty.
        TenantIsolationError: If any returned chunk has a non-matching tenant_id.
    """
    clean_tenant_id = tenant_id.strip().lower() if tenant_id else ""
    clean_question = question.strip() if question else ""

    if not clean_tenant_id:
        raise ValueError("tenant_id must be provided and cannot be empty.")

    if not clean_question:
        raise ValueError("question must be provided and cannot be empty.")

    if top_k <= 0:
        raise ValueError("top_k must be an integer greater than 0.")

    # 1. Validate tenant against tenants.yaml
    tenant_cfg: TenantConfig = get_tenant(clean_tenant_id)
    collection_name = tenant_cfg.collection_name

    logger.info(
        "Initiating tenant retrieval for '%s' (%s) in collection '%s' (top_k=%d)",
        tenant_cfg.id,
        tenant_cfg.name,
        collection_name,
        top_k,
    )

    # 2. Acquire Chroma client and dedicated collection
    if client is None:
        client = get_chroma_client()

    try:
        collection = client.get_collection(name=collection_name)
    except Exception as exc:
        raise CollectionNotFoundError(
            f"Collection '{collection_name}' for tenant '{clean_tenant_id}' was not found. "
            f"Has the ingestion pipeline been executed for this tenant?"
        ) from exc

    total_chunks = collection.count()
    if total_chunks == 0:
        logger.warning(
            "Collection '%s' for tenant '%s' is empty.",
            collection_name,
            clean_tenant_id,
        )
        return []

    # 3. Embed question with Qwen3-Embedding-0.6B
    if embedder is None:
        embedder = get_embedder()

    logger.debug("Generating query embedding for: '%s'", clean_question)
    query_embedding = embedder.embed_text(clean_question)

    # 4. Query ONLY the tenant-dedicated collection
    actual_k = min(top_k, total_chunks)
    query_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=actual_k,
        include=["documents", "metadatas", "distances"],
    )

    documents_batch = query_results.get("documents", [[]])[0]
    metadatas_batch = query_results.get("metadatas", [[]])[0]
    distances_batch = query_results.get("distances", [[]])[0]
    ids_batch = query_results.get("ids", [[]])[0]

    retrieved_chunks: List[RetrievedChunk] = []

    # 5. Strict Zero-Trust Post-Retrieval Isolation Audit
    for chunk_id, doc_text, metadata, distance in zip(
        ids_batch, documents_batch, metadatas_batch, distances_batch
    ):
        chunk_tenant = str(metadata.get("tenant_id", "")).strip().lower()

        # HARD ASSERTION: Verify chunk tenant_id against requested tenant
        if chunk_tenant != clean_tenant_id:
            logger.critical(
                "DATA CONTAMINATION DETECTED! Expected tenant '%s', but chunk '%s' "
                "in collection '%s' has tenant_id='%s'!",
                clean_tenant_id,
                chunk_id,
                collection_name,
                chunk_tenant,
            )
            raise TenantIsolationError(
                f"Cross-tenant data contamination detected: Chunk '{chunk_id}' has "
                f"tenant_id='{chunk_tenant}', which does not match requested tenant='{clean_tenant_id}'."
            )

        # Cosine distance to similarity: similarity = 1 - distance
        similarity = max(0.0, 1.0 - distance) if distance is not None else None

        p_start = int(metadata.get("page_start") or metadata.get("page_number", 1))
        p_end = int(metadata.get("page_end") or p_start)
        p_num = int(metadata.get("page_number") or p_start)

        chunk = RetrievedChunk(
            chunk_id=str(chunk_id),
            text=str(doc_text),
            tenant_id=chunk_tenant,
            source_file=str(metadata.get("source_file", "")),
            page_number=p_num,
            page_start=p_start,
            page_end=p_end,
            chunk_index=int(metadata.get("chunk_index", 0)),
            token_count=int(metadata.get("token_count", 0)),
            distance=float(distance) if distance is not None else None,
            similarity=similarity,
            metadata=dict(metadata),
        )
        retrieved_chunks.append(chunk)

    logger.info(
        "Successfully retrieved and verified %d isolated chunks for tenant '%s'.",
        len(retrieved_chunks),
        clean_tenant_id,
    )
    return retrieved_chunks
