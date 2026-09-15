"""Ingestion runner module for Multi-Tenant RAG System.

Reads tenants.yaml, loads each tenant handbook, segments into semantic chunks,
generates embeddings with Qwen3-Embedding-0.6B, and persists vectors into
isolated, dedicated Chroma collections per tenant with tenant_id tagging safeguards.
"""

from typing import Dict, List, Optional
import argparse
import logging
import sys
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings

from ingestion.config import (
    load_tenants_config,
    get_tenant,
    get_settings,
    TenantConfig,
    PROJECT_ROOT,
)
from ingestion.loader import load_tenant_document, DocumentPage
from ingestion.chunking import chunk_tenant_document, DocumentChunk
from ingestion.embedder import get_embedder, QwenEmbedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ingestion.ingest")


def get_chroma_client(persist_directory: Optional[Path | str] = None) -> chromadb.PersistentClient:
    """Initialize a persistent ChromaDB client for vector storage."""
    settings = get_settings()
    target_dir = Path(persist_directory) if persist_directory else settings.resolved_chroma_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(target_dir),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def ingest_tenant(
    tenant_cfg: TenantConfig,
    client: Optional[chromadb.PersistentClient] = None,
    embedder: Optional[QwenEmbedder] = None,
    reset_collection: bool = False,
) -> int:
    """Ingest a single tenant handbook into its dedicated, isolated Chroma collection.

    Args:
        tenant_cfg: Configuration object for the tenant.
        client: Persistent Chroma client (creates new if None).
        embedder: Local embedding generator (initializes default if None).
        reset_collection: If True, deletes existing collection before re-indexing.

    Returns:
        Number of chunks indexed.
    """
    tenant_id = tenant_cfg.id
    collection_name = tenant_cfg.collection_name
    logger.info("=" * 60)
    logger.info("Starting ingestion for tenant: '%s' (%s)", tenant_id, tenant_cfg.name)
    logger.info("Dedicated collection: '%s'", collection_name)
    logger.info("Handbook path: '%s'", tenant_cfg.resolved_pdf_path)
    logger.info("=" * 60)

    if client is None:
        client = get_chroma_client()

    if embedder is None:
        embedder = get_embedder()

    # Step 1: Load and extract text pages from PDF
    pages: List[DocumentPage] = load_tenant_document(tenant_id)
    if not pages:
        raise ValueError(f"No pages extracted from handbook for tenant '{tenant_id}'.")
    logger.info("Extracted %d pages from '%s'.", len(pages), tenant_cfg.resolved_pdf_path.name)

    # Step 2: Split pages into overlapping semantic chunks
    chunks: List[DocumentChunk] = chunk_tenant_document(pages)
    if not chunks:
        raise ValueError(f"No chunks generated for tenant '{tenant_id}'.")
    logger.info(
        "Generated %d semantic chunks (~600 tokens target, 15%% overlap).",
        len(chunks),
    )

    # Step 3: Handle collection initialization / reset
    if reset_collection:
        try:
            client.delete_collection(name=collection_name)
            logger.info("Reset existing collection '%s'.", collection_name)
        except Exception:
            pass  # Collection does not exist yet

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "tenant_id": tenant_id,
            "tenant_name": tenant_cfg.name,
            "description": tenant_cfg.description or "",
            "hnsw:space": "cosine",
        },
    )

    # Step 4: Extract chunk texts, IDs, and metadata (with tenant_id safeguard)
    chunk_texts = [chunk.text for chunk in chunks]
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    chunk_metadatas = []

    for chunk in chunks:
        # Enforce tenant isolation tagging as a secondary safeguard
        meta = {
            "tenant_id": str(tenant_id),
            "chunk_id": str(chunk.chunk_id),
            "source_file": str(chunk.source_file),
            "page_start": int(chunk.page_start),
            "page_end": int(chunk.page_end),
            "chunk_index": int(chunk.chunk_index),
            "token_count": int(chunk.token_count),
        }
        chunk_metadatas.append(meta)

    # Step 5: Compute local vector embeddings
    logger.info("Generating embeddings using model '%s'...", embedder.model_name)
    embeddings = embedder.embed_documents(chunk_texts)
    logger.info("Computed %d embeddings (dimension: %d).", len(embeddings), len(embeddings[0]))

    # Step 6: Store vectors and metadata in dedicated collection
    collection.upsert(
        ids=chunk_ids,
        embeddings=embeddings,
        documents=chunk_texts,
        metadatas=chunk_metadatas,
    )

    total_in_collection = collection.count()
    logger.info(
        "Successfully indexed %d chunks for tenant '%s' into collection '%s'. (Total vectors: %d)",
        len(chunks),
        tenant_id,
        collection_name,
        total_in_collection,
    )
    return len(chunks)


def run_ingestion(
    tenant_filter: Optional[str] = None,
    reset: bool = False,
    config_path: Optional[Path | str] = None,
) -> Dict[str, int]:
    """Execute ingestion pipeline for all configured tenants or a specific tenant.

    Args:
        tenant_filter: Optional specific tenant ID to process.
        reset: Whether to delete existing collections before indexing.
        config_path: Optional path to custom tenants.yaml.

    Returns:
        Dictionary mapping tenant ID to number of indexed chunks.
    """
    tenants = load_tenants_config(config_path=config_path, verify_files=True)

    if tenant_filter:
        clean_filter = tenant_filter.strip().lower()
        if clean_filter not in tenants:
            raise ValueError(
                f"Requested tenant '{tenant_filter}' not found in configuration. "
                f"Available tenants: {list(tenants.keys())}"
            )
        target_tenants = {clean_filter: tenants[clean_filter]}
    else:
        target_tenants = tenants

    client = get_chroma_client()
    embedder = get_embedder()

    results: Dict[str, int] = {}
    for tenant_id, tenant_cfg in target_tenants.items():
        count = ingest_tenant(
            tenant_cfg=tenant_cfg,
            client=client,
            embedder=embedder,
            reset_collection=reset,
        )
        results[tenant_id] = count

    logger.info("=" * 60)
    logger.info("Ingestion completed successfully for %d tenant(s).", len(results))
    for t_id, cnt in results.items():
        logger.info(" - Tenant '%s': %d chunks indexed", t_id, cnt)
    logger.info("=" * 60)
    return results


def main():
    """Command-line entrypoint for running ingestion."""
    parser = argparse.ArgumentParser(
        description="Multi-Tenant RAG Data Ingestion Pipeline (Qwen3-Embedding-0.6B + Chroma)"
    )
    parser.add_argument(
        "--tenant",
        type=str,
        default=None,
        help="Specify single tenant to ingest (e.g., 'acme', 'globex'). Defaults to all tenants.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset/wipe existing Chroma collections before indexing.",
    )
    args = parser.parse_args()

    try:
        run_ingestion(tenant_filter=args.tenant, reset=args.reset)
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
