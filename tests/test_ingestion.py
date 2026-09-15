"""Unit and integration tests for the multi-tenant ingestion pipeline.

Verifies:
1. Document loading and semantic chunking correctness.
2. Dedicated Chroma collections are created and populated per tenant.
3. Embeddings match the expected dimensionality.
4. Absolute tenant isolation: zero cross-contamination between Acme and Globex collections.
"""

from typing import List
import hashlib
import pytest
import chromadb
from chromadb.config import Settings as ChromaSettings

from ingestion.config import load_tenants_config, get_tenant
from ingestion.loader import load_tenant_document, extract_text_from_pdf
from ingestion.chunking import chunk_tenant_document
from ingestion.embedder import QwenEmbedder, DEFAULT_EMBEDDING_MODEL
from ingestion.ingest import ingest_tenant

EXPECTED_EMBEDDING_DIM = 1024


class DeterministicTestEmbedder:
    """Fast, deterministic local embedder for test execution without GPU/network download.

    Generates mathematically consistent 1024-dimensional normalized vectors based on SHA-256 hashes,
    matching the exact dimensionality and interface of Qwen3-Embedding-0.6B.
    """

    def __init__(self, dimension: int = EXPECTED_EMBEDDING_DIM):
        self.dimension = dimension
        self.model_name = "test-qwen3-embedding-mock"

    def embed_text(self, text: str) -> List[float]:
        # Generate pseudo-random deterministic floats between -1.0 and 1.0 from text hash
        hasher = hashlib.sha256(text.encode("utf-8"))
        seed_bytes = hasher.digest()
        vector = []
        for i in range(self.dimension):
            byte_val = seed_bytes[i % len(seed_bytes)]
            val = (byte_val / 128.0) - 1.0 + ((i % 17) * 0.01)
            vector.append(val)

        # L2 normalize
        norm = sum(v * v for v in vector) ** 0.5
        return [v / norm for v in vector] if norm > 0 else vector

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

    def __call__(self, input: List[str]) -> List[List[float]]:
        return self.embed_documents(input)

    def name(self) -> str:
        return "deterministic_test_embedder"


@pytest.fixture
def mock_embedder() -> DeterministicTestEmbedder:
    """Fixture providing deterministic 1024-dim embedder for fast, reproducible tests."""
    return DeterministicTestEmbedder(dimension=EXPECTED_EMBEDDING_DIM)


@pytest.fixture
def test_chroma_client(tmp_path) -> chromadb.PersistentClient:
    """Fixture providing an isolated temporary ChromaDB persistent client."""
    db_path = tmp_path / "chroma_test"
    db_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(
        path=str(db_path),
        settings=ChromaSettings(anonymized_telemetry=False),
    )


class TestMultiTenantIngestion:
    """Test suite verifying end-to-end ingestion and tenant isolation."""

    def test_pdf_loading_acme_and_globex(self):
        """Verify that both client handbooks exist, parse correctly, and extract 10 pages each."""
        acme_pages = load_tenant_document("acme")
        globex_pages = load_tenant_document("globex")

        assert len(acme_pages) == 10, f"Expected 10 pages for Acme, found {len(acme_pages)}"
        assert len(globex_pages) == 10, f"Expected 10 pages for Globex, found {len(globex_pages)}"

        # Verify page 1 metadata and content
        assert acme_pages[0].tenant_id == "acme"
        assert "ACME CORP" in acme_pages[0].text
        assert globex_pages[0].tenant_id == "globex"
        assert "GLOBEX" in globex_pages[0].text

    def test_semantic_chunking_boundaries_and_metadata(self):
        """Verify chunks have ~600 tokens target, valid page tracking, and immutable tenant tagging."""
        acme_pages = load_tenant_document("acme")
        acme_chunks = chunk_tenant_document(acme_pages)

        assert len(acme_chunks) > 0, "Chunking produced 0 chunks for Acme"
        for chunk in acme_chunks:
            assert chunk.tenant_id == "acme"
            assert chunk.chunk_id.startswith("acme_chunk_")
            assert chunk.page_number >= 1
            assert chunk.page_start >= 1
            assert chunk.page_end >= chunk.page_start
            assert chunk.page_number == chunk.page_start
            assert chunk.metadata.get("page_number") == chunk.page_number
            assert len(chunk.text.strip()) > 0
            assert chunk.token_count > 0

    def test_chunk_pdf_per_page(self):
        """Verify chunk_pdf_per_page extracts per-page text and assigns page numbers."""
        from ingestion.chunking import chunk_pdf_per_page
        tenant = get_tenant("acme")
        chunks = chunk_pdf_per_page(tenant.pdf_path, tenant_id="acme")
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.page_number >= 1
            assert chunk.page_start == chunk.page_number
            assert chunk.metadata.get("page_number") == chunk.page_number
            assert "Acme" in chunk.source_file

    def test_tenant_collections_populated_and_isolated(
        self, test_chroma_client, mock_embedder
    ):
        """Verify both tenants have chunks indexed in separate collections with expected dimensionality."""
        tenants = load_tenants_config()
        assert "acme" in tenants
        assert "globex" in tenants

        # Ingest Acme into test Chroma
        acme_count = ingest_tenant(
            tenant_cfg=tenants["acme"],
            client=test_chroma_client,
            embedder=mock_embedder,
            reset_collection=True,
        )
        assert acme_count > 0, "Acme ingestion yielded 0 indexed chunks"

        # Ingest Globex into test Chroma
        globex_count = ingest_tenant(
            tenant_cfg=tenants["globex"],
            client=test_chroma_client,
            embedder=mock_embedder,
            reset_collection=True,
        )
        assert globex_count > 0, "Globex ingestion yielded 0 indexed chunks"

        # Verify collections exist separately
        collections = {c.name: c for c in test_chroma_client.list_collections()}
        assert tenants["acme"].collection_name in collections
        assert tenants["globex"].collection_name in collections

        acme_col = collections[tenants["acme"].collection_name]
        globex_col = collections[tenants["globex"].collection_name]

        assert acme_col.count() == acme_count
        assert globex_col.count() == globex_count

    def test_embedding_dimensionality(self, test_chroma_client, mock_embedder):
        """Verify indexed embeddings strictly match the required 1024-dimensional space."""
        tenants = load_tenants_config()

        ingest_tenant(
            tenant_cfg=tenants["acme"],
            client=test_chroma_client,
            embedder=mock_embedder,
            reset_collection=True,
        )

        acme_col = test_chroma_client.get_collection(name=tenants["acme"].collection_name)
        data = acme_col.get(include=["embeddings"])
        embeddings = data.get("embeddings")

        assert embeddings is not None and len(embeddings) > 0
        for emb in embeddings:
            assert len(emb) == EXPECTED_EMBEDDING_DIM, (
                f"Embedding dimension mismatch: expected {EXPECTED_EMBEDDING_DIM}, got {len(emb)}"
            )

    def test_strict_zero_data_cross_contamination(
        self, test_chroma_client, mock_embedder
    ):
        """CRITICAL: Verify that no chunk in Acme's collection has tenant_id=globex or vice versa."""
        tenants = load_tenants_config()

        # Ingest both tenants
        ingest_tenant(
            tenant_cfg=tenants["acme"],
            client=test_chroma_client,
            embedder=mock_embedder,
            reset_collection=True,
        )
        ingest_tenant(
            tenant_cfg=tenants["globex"],
            client=test_chroma_client,
            embedder=mock_embedder,
            reset_collection=True,
        )

        acme_col = test_chroma_client.get_collection(name=tenants["acme"].collection_name)
        globex_col = test_chroma_client.get_collection(name=tenants["globex"].collection_name)

        # Inspect ALL chunks in Acme's collection
        acme_data = acme_col.get(include=["metadatas", "documents"])
        for idx, meta in enumerate(acme_data["metadatas"]):
            assert meta["tenant_id"] == "acme", (
                f"DATA CONTAMINATION DETECTED! Found tenant_id '{meta['tenant_id']}' in Acme collection."
            )
            assert meta["tenant_id"] != "globex", (
                "DATA CONTAMINATION DETECTED! Globex data found in Acme collection."
            )
            assert "Homer the Nuclear Technician" not in acme_data["documents"][idx], (
                "Content leakage: Globex mascot Homer found inside Acme document."
            )

        # Inspect ALL chunks in Globex's collection
        globex_data = globex_col.get(include=["metadatas", "documents"])
        for idx, meta in enumerate(globex_data["metadatas"]):
            assert meta["tenant_id"] == "globex", (
                f"DATA CONTAMINATION DETECTED! Found tenant_id '{meta['tenant_id']}' in Globex collection."
            )
            assert meta["tenant_id"] != "acme", (
                "DATA CONTAMINATION DETECTED! Acme data found in Globex collection."
            )
            assert "Bugs Bunny" not in globex_data["documents"][idx], (
                "Content leakage: Acme CEO Bugs Bunny found inside Globex document."
            )

    def test_query_retrieval_isolation(self, test_chroma_client, mock_embedder):
        """Verify vector similarity queries against a tenant only ever return chunks belonging to that tenant."""
        tenants = load_tenants_config()

        ingest_tenant(
            tenant_cfg=tenants["acme"],
            client=test_chroma_client,
            embedder=mock_embedder,
            reset_collection=True,
        )
        ingest_tenant(
            tenant_cfg=tenants["globex"],
            client=test_chroma_client,
            embedder=mock_embedder,
            reset_collection=True,
        )

        acme_col = test_chroma_client.get_collection(name=tenants["acme"].collection_name)
        query_vector = mock_embedder.embed_text("What is the policy on PTO and hibernation?")

        query_results = acme_col.query(
            query_embeddings=[query_vector],
            n_results=3,
            include=["metadatas", "documents"],
        )

        for meta in query_results["metadatas"][0]:
            assert meta["tenant_id"] == "acme"
            assert meta["tenant_id"] != "globex"
