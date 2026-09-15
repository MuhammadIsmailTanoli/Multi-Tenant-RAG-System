"""Unit tests for tenant-scoped retrieval in api/retriever.py.

Verifies:
1. Question is embedded and queried against the tenant's dedicated collection.
2. Top-k chunks are returned with proper metadata.
3. Every returned chunk has tenant_id matching the request.
4. Hard security assertion: TenantIsolationError is raised if any foreign chunk is present.
5. Unknown tenant, empty question, or invalid parameters raise expected exceptions.
"""

from typing import List
import pytest
import chromadb
from chromadb.config import Settings as ChromaSettings

from api.retriever import (
    retrieve_tenant_chunks,
    RetrievedChunk,
    TenantIsolationError,
    CollectionNotFoundError,
)
from tests.test_ingestion import DeterministicTestEmbedder


@pytest.fixture
def mock_isolated_chroma():
    """Create an in-memory Chroma client with isolated collections for testing."""
    client = chromadb.EphemeralClient(settings=ChromaSettings(anonymized_telemetry=False))
    embedder = DeterministicTestEmbedder()

    # 1. Populate tenant_acme collection with Acme-tagged chunks
    try:
        client.delete_collection("tenant_acme")
    except Exception:
        pass
    acme_col = client.get_or_create_collection("tenant_acme", metadata={"hnsw:space": "cosine"})
    acme_texts = [
        "Acme safety protocols require protective helmets and certified goggles.",
        "Acme probationary period for all employees is strictly 90 days.",
    ]
    acme_col.add(
        ids=["acme_chunk_1", "acme_chunk_2"],
        documents=acme_texts,
        embeddings=embedder.embed_documents(acme_texts),
        metadatas=[
            {"tenant_id": "acme", "source_file": "Acme.pdf", "page_start": 1, "page_end": 2, "chunk_index": 0, "token_count": 50},
            {"tenant_id": "acme", "source_file": "Acme.pdf", "page_start": 3, "page_end": 4, "chunk_index": 1, "token_count": 55},
        ],
    )

    # 2. Populate tenant_globex collection with Globex-tagged chunks
    try:
        client.delete_collection("tenant_globex")
    except Exception:
        pass
    globex_col = client.get_or_create_collection("tenant_globex", metadata={"hnsw:space": "cosine"})
    globex_texts = [
        "Globex high-security facilities enforce biometric clearance at all checkpoints.",
        "Globex probationary period is 180 days with quarterly evaluations.",
    ]
    globex_col.add(
        ids=["globex_chunk_1", "globex_chunk_2"],
        documents=globex_texts,
        embeddings=embedder.embed_documents(globex_texts),
        metadatas=[
            {"tenant_id": "globex", "source_file": "Globex.pdf", "page_start": 1, "page_end": 2, "chunk_index": 0, "token_count": 60},
            {"tenant_id": "globex", "source_file": "Globex.pdf", "page_start": 3, "page_end": 5, "chunk_index": 1, "token_count": 65},
        ],
    )

    return client, embedder


def test_retriever_fetches_acme_chunks(mock_isolated_chroma):
    """Verify retrieval returns Acme chunks when querying tenant 'acme'."""
    client, embedder = mock_isolated_chroma
    chunks = retrieve_tenant_chunks(
        tenant_id="acme",
        question="What is the probationary period?",
        top_k=2,
        client=client,
        embedder=embedder,
    )
    assert len(chunks) == 2
    for chunk in chunks:
        assert isinstance(chunk, RetrievedChunk)
        assert chunk.tenant_id == "acme"
        assert chunk.source_file == "Acme.pdf"
        assert chunk.similarity is not None


def test_retriever_fetches_globex_chunks(mock_isolated_chroma):
    """Verify retrieval returns Globex chunks when querying tenant 'globex'."""
    client, embedder = mock_isolated_chroma
    chunks = retrieve_tenant_chunks(
        tenant_id="globex",
        question="What are the security clearance rules?",
        top_k=2,
        client=client,
        embedder=embedder,
    )
    assert len(chunks) == 2
    for chunk in chunks:
        assert isinstance(chunk, RetrievedChunk)
        assert chunk.tenant_id == "globex"
        assert chunk.source_file == "Globex.pdf"


def test_retriever_raises_tenant_isolation_error_on_foreign_chunk(mock_isolated_chroma):
    """Verify hard assertion: TenantIsolationError is raised if a foreign chunk is retrieved."""
    client, embedder = mock_isolated_chroma

    # Intentionally corrupt the acme collection by inserting a globex-tagged chunk
    acme_col = client.get_collection("tenant_acme")
    rogue_text = ["Rogue chunk from Globex infiltrated into Acme collection."]
    acme_col.add(
        ids=["rogue_globex_chunk"],
        documents=rogue_text,
        embeddings=embedder.embed_documents(rogue_text),
        metadatas=[{"tenant_id": "globex", "source_file": "Globex.pdf", "page_start": 1, "page_end": 1, "chunk_index": 99, "token_count": 20}],
    )

    # When querying Acme, if the rogue globex chunk is hit, TenantIsolationError MUST be raised
    with pytest.raises(TenantIsolationError) as exc_info:
        retrieve_tenant_chunks(
            tenant_id="acme",
            question="Rogue chunk from Globex",
            top_k=3,
            client=client,
            embedder=embedder,
        )
    assert "Cross-tenant data contamination detected" in str(exc_info.value)
    assert "tenant_id='globex'" in str(exc_info.value)


def test_retriever_validation_errors(mock_isolated_chroma):
    """Verify input validation for tenant_id, question, and top_k."""
    client, embedder = mock_isolated_chroma

    # Unknown tenant
    with pytest.raises(ValueError, match="Unknown tenant"):
        retrieve_tenant_chunks("unknown_tenant", "valid question", client=client, embedder=embedder)

    # Empty question
    with pytest.raises(ValueError, match="question must be provided"):
        retrieve_tenant_chunks("acme", "   ", client=client, embedder=embedder)

    # Invalid top_k
    with pytest.raises(ValueError, match="top_k must be an integer greater than 0"):
        retrieve_tenant_chunks("acme", "valid question", top_k=0, client=client, embedder=embedder)
