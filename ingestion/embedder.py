"""Local embedding module using Qwen3-Embedding-0.6B.

Generates dense vector embeddings locally without external API keys,
enforcing privacy and zero network dependency during ingestion and retrieval.
"""

from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"


class QwenEmbedder:
    """Local embedding generator utilizing the Qwen3-Embedding-0.6B model.

    Implements Chroma's EmbeddingFunction interface so it can be seamlessly passed
    to Chroma collections, while also providing standalone embedding methods.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        device: Optional[str] = None,
        normalize_embeddings: bool = True,
    ):
        """Initialize the sentence transformer embedding model.

        Args:
            model_name: HuggingFace model repo ID (default: Qwen/Qwen3-Embedding-0.6B).
            device: Computing device ('cuda', 'cpu', or None for auto-detection).
            normalize_embeddings: Whether to L2-normalize vectors for cosine similarity.
        """
        self.model_name = model_name
        self.normalize_embeddings = normalize_embeddings
        self._model = None
        self._device = device

    def _load_model(self):
        """Lazy-load the SentenceTransformer model upon first request."""
        if self._model is None:
            try:
                import torch
                from sentence_transformers import SentenceTransformer

                if self._device is None:
                    self._device = "cuda" if torch.cuda.is_available() else "cpu"

                logger.info(
                    "Loading local embedding model '%s' on device '%s'...",
                    self.model_name,
                    self._device,
                )
                self._model = SentenceTransformer(
                    self.model_name,
                    device=self._device,
                )
                logger.info("Successfully loaded embedding model '%s'.", self.model_name)
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers and torch are required for local embeddings. "
                    "Install them using: pip install sentence-transformers torch"
                ) from exc
            except Exception as exc:
                logger.error("Failed to load model '%s': %s", self.model_name, exc)
                raise
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Generate a vector embedding for a single text query.

        Args:
            text: Input text string.

        Returns:
            List of floats representing the dense vector embedding.
        """
        model = self._load_model()
        embedding = model.encode(
            text,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=False,
        )
        return embedding.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for a batch of documents.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of vector embeddings (lists of floats).
        """
        if not texts:
            return []

        model = self._load_model()
        embeddings = model.encode(
            texts,
            normalize_embeddings=self.normalize_embeddings,
            show_progress_bar=len(texts) > 20,
            batch_size=32,
        )
        return embeddings.tolist()

    def __call__(self, input: List[str]) -> List[List[float]]:
        """Chroma-compatible EmbeddingFunction signature."""
        return self.embed_documents(input)

    def name(self) -> str:
        """Chroma EmbeddingFunction identifier name."""
        return f"qwen_embedding_{self.model_name.replace('/', '_')}"


_EMBEDDER_INSTANCE: Optional[QwenEmbedder] = None


def get_embedder(
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    device: Optional[str] = None,
) -> QwenEmbedder:
    """Retrieve or initialize the singleton QwenEmbedder instance."""
    global _EMBEDDER_INSTANCE
    if _EMBEDDER_INSTANCE is None or _EMBEDDER_INSTANCE.model_name != model_name:
        _EMBEDDER_INSTANCE = QwenEmbedder(model_name=model_name, device=device)
    return _EMBEDDER_INSTANCE
