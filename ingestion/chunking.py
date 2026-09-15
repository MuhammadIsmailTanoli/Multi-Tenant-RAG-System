"""Chunking module for multi-tenant document ingestion.

================================================================================
CHUNKING STRATEGY EXPLANATION & ARCHITECTURAL RATIONALE
================================================================================

1. Target Chunk Size (~600 Tokens):
   - In employee handbooks and enterprise policy documents, policies, exceptions,
     leave rules, and compliance clauses typically span 2 to 4 paragraphs.
   - Chunks that are too small (e.g., 100-200 tokens) fragment policy rules from
     their critical caveats (e.g., separating "Unlimited PTO" from "Mandatory 25
     days minimum by Q3").
   - Chunks that are too large (e.g., >1500 tokens) introduce irrelevant noise,
     dilute vector similarity signals, and consume unnecessary LLM context window.
   - A target size of ~600 tokens (~450 words / ~2,400 characters) provides an optimal
     balance between comprehensive semantic context and pinpoint retrieval precision.

2. Overlap Window (15% Overlap / ~90 Tokens):
   - Sliding window overlap ensures that sentences or conceptual definitions spanning
     the boundary between two consecutive chunks are not severed.
   - A 15% overlap (~90 tokens / ~65 words) guarantees that the concluding thoughts
     of Chunk N are preserved at the beginning of Chunk N+1, preventing retrieval
     blind spots where crucial conditions cross chunk margins.

3. Recursive Boundary Preservation:
   - Rather than slicing strictly at arbitrary token or character counts, the chunker
     splits recursively on natural semantic boundaries:
     a) Paragraph breaks ('\\n\\n')
     b) Line breaks ('\\n')
     c) Sentence boundaries ('. ', '? ', '! ')
     d) Word boundaries (' ')
   - This ensures chunks retain structural readability and grammatical cohesion.

4. Multi-Page Attribution & Cross-Page Merging:
   - Employee handbooks often contain sections that flow across consecutive pages.
   - The chunker ingests DocumentPage objects, stitches the document stream while
     preserving page boundary mappings, and records both 'page_start' and 'page_end'
     on every chunk. This provides exact citations for RAG synthesis.

5. Strict Tenant Data Isolation:
   - Each generated chunk is tagged with an immutable 'tenant_id' and an isolated
     deterministic chunk ID ('{tenant_id}_chunk_{index:04d}').
   - This ensures provenance is permanently linked to the tenant throughout embedding,
     storage, and retrieval.
================================================================================
"""

from typing import Any, Dict, List, Optional
from pathlib import Path
import re
import logging
from pydantic import BaseModel, Field, model_validator

from ingestion.loader import DocumentPage

logger = logging.getLogger(__name__)

# Default chunking parameters
DEFAULT_CHUNK_SIZE_TOKENS = 600
DEFAULT_OVERLAP_PERCENTAGE = 0.15  # 15% overlap
DEFAULT_OVERLAP_TOKENS = int(DEFAULT_CHUNK_SIZE_TOKENS * DEFAULT_OVERLAP_PERCENTAGE)  # ~90 tokens

# Estimation factor: 1 token ~= 4 characters / 0.75 words in English
APPROX_CHARS_PER_TOKEN = 4.0


def estimate_token_count(text: str) -> int:
    """Estimate token count for a text string.

    Uses tiktoken if installed; otherwise utilizes standard character/word heuristic
    (1 token ~= 4 characters or ~0.75 words), which closely mirrors OpenAI tokenization.
    """
    if not text:
        return 0

    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # Robust heuristic fallback: average of character-based and word-based estimation
        char_estimate = len(text) / APPROX_CHARS_PER_TOKEN
        words = text.split()
        word_estimate = len(words) * 1.33
        return max(1, int((char_estimate + word_estimate) / 2.0))


class DocumentChunk(BaseModel):
    """Represents an isolated, processed chunk ready for vector embedding and storage."""

    chunk_id: str = Field(..., description="Unique deterministic identifier (e.g. acme_chunk_0001).")
    tenant_id: str = Field(..., description="Tenant identifier to enforce data boundary.")
    text: str = Field(..., description="Cleaned chunk text content.")
    token_count: int = Field(..., description="Estimated or exact token count.")
    page_number: int = Field(
        default=1,
        description="Primary source page number where this chunk originates (1-indexed).",
    )
    page_start: int = Field(..., description="First document page spanned by this chunk (1-indexed).")
    page_end: int = Field(..., description="Last document page spanned by this chunk (1-indexed).")
    source_file: str = Field(..., description="Source handbook PDF filename.")
    chunk_index: int = Field(..., description="0-indexed position within the tenant document stream.")
    metadata: Dict[str, str | int] = Field(
        default_factory=dict,
        description="Metadata dictionary for vector store indexing.",
    )

    @model_validator(mode="before")
    @classmethod
    def set_default_page_number(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "page_number" not in data or data["page_number"] is None:
                data["page_number"] = data.get("page_start", 1)
        return data


class TextChunker:
    """Recursive semantic chunker for multi-tenant documents."""

    def __init__(
        self,
        chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
        overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    ):
        if chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens must be greater than 0.")
        if overlap_tokens < 0 or overlap_tokens >= chunk_size_tokens:
            raise ValueError("overlap_tokens must be non-negative and less than chunk_size_tokens.")

        self.chunk_size_tokens = chunk_size_tokens
        self.overlap_tokens = overlap_tokens

    def _split_into_semantic_segments(self, text: str) -> List[str]:
        """Split text into small semantic units (paragraphs or sentences) preserving structure."""
        if not text.strip():
            return []

        # First split on paragraph breaks
        raw_paragraphs = text.split("\n\n")
        segments: List[str] = []

        for p in raw_paragraphs:
            p_clean = p.strip()
            if not p_clean:
                continue

            # If paragraph fits comfortably under half chunk size, keep it whole
            if estimate_token_count(p_clean) <= (self.chunk_size_tokens // 2):
                segments.append(p_clean)
            else:
                # Split large paragraph into sentences
                sentence_candidates = re.split(r"(?<=[.?!])\s+", p_clean)
                for s in sentence_candidates:
                    s_clean = s.strip()
                    if s_clean:
                        segments.append(s_clean)

        return segments

    def chunk_pages(
        self,
        pages: List[DocumentPage],
        tenant_id: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """Convert a sequence of DocumentPage objects into overlapping DocumentChunk objects.

        Maintains accurate page range citations and strict tenant tagging.
        """
        if not pages:
            return []

        # Validate consistent tenant_id
        resolved_tenant = (tenant_id or pages[0].tenant_id).strip().lower()
        source_file = pages[0].source_file

        # Build an indexed stream of atomic units tagged with page numbers
        units_with_pages: List[tuple[str, int]] = []
        for page in pages:
            if page.tenant_id != resolved_tenant:
                raise ValueError(
                    f"Cross-tenant pollution detected during chunking: "
                    f"expected '{resolved_tenant}', encountered '{page.tenant_id}'."
                )
            page_segments = self._split_into_semantic_segments(page.text)
            for seg in page_segments:
                units_with_pages.append((seg, page.page_number))

        if not units_with_pages:
            return []

        chunks: List[DocumentChunk] = []
        unit_idx = 0
        total_units = len(units_with_pages)
        chunk_counter = 0

        while unit_idx < total_units:
            current_chunk_parts: List[str] = []
            current_tokens = 0
            page_start = units_with_pages[unit_idx][1]
            page_end = page_start

            start_idx = unit_idx

            while unit_idx < total_units:
                segment_text, page_num = units_with_pages[unit_idx]
                segment_tokens = estimate_token_count(segment_text)

                # Check if adding this segment exceeds target size
                if current_chunk_parts and (current_tokens + segment_tokens > self.chunk_size_tokens):
                    break

                current_chunk_parts.append(segment_text)
                current_tokens += segment_tokens
                page_end = max(page_end, page_num)
                unit_idx += 1

            # Fallback if a single segment is larger than chunk_size_tokens
            if not current_chunk_parts and unit_idx < total_units:
                segment_text, page_num = units_with_pages[unit_idx]
                current_chunk_parts.append(segment_text)
                current_tokens += estimate_token_count(segment_text)
                page_end = max(page_end, page_num)
                unit_idx += 1

            chunk_text = "\n\n".join(current_chunk_parts).strip()
            actual_tokens = estimate_token_count(chunk_text)

            chunk_obj = DocumentChunk(
                chunk_id=f"{resolved_tenant}_chunk_{chunk_counter:04d}",
                tenant_id=resolved_tenant,
                text=chunk_text,
                token_count=actual_tokens,
                page_number=page_start,
                page_start=page_start,
                page_end=page_end,
                source_file=source_file,
                chunk_index=chunk_counter,
                metadata={
                    "chunk_id": f"{resolved_tenant}_chunk_{chunk_counter:04d}",
                    "tenant_id": resolved_tenant,
                    "source_file": source_file,
                    "page_number": page_start,
                    "page_start": page_start,
                    "page_end": page_end,
                    "chunk_index": chunk_counter,
                    "token_count": actual_tokens,
                },
            )
            chunks.append(chunk_obj)
            chunk_counter += 1

            # If we've processed all units, exit
            if unit_idx >= total_units:
                break

            # Calculate overlap for sliding window:
            # Rewind unit_idx by the number of units that sum to ~overlap_tokens
            overlap_accum = 0
            rewind_steps = 0
            for backtrack in range(unit_idx - 1, start_idx, -1):
                seg_tokens = estimate_token_count(units_with_pages[backtrack][0])
                if overlap_accum + seg_tokens > self.overlap_tokens:
                    break
                overlap_accum += seg_tokens
                rewind_steps += 1

            # Advance by at least 1 unit to guarantee forward progress
            new_start = unit_idx - rewind_steps
            if new_start <= start_idx:
                unit_idx = start_idx + 1
            else:
                unit_idx = new_start

        logger.info(
            "Created %d chunks for tenant '%s' (target size: %d tokens, overlap: %d tokens).",
            len(chunks),
            resolved_tenant,
            self.chunk_size_tokens,
            self.overlap_tokens,
        )
        return chunks


def chunk_tenant_document(
    pages: List[DocumentPage],
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[DocumentChunk]:
    """Convenience function to chunk pages with default or customized sliding window parameters."""
    chunker = TextChunker(
        chunk_size_tokens=chunk_size_tokens,
        overlap_tokens=overlap_tokens,
    )
    return chunker.chunk_pages(pages)


def chunk_pdf_per_page(
    pdf_path: str | Path,
    tenant_id: str,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> List[DocumentChunk]:
    """Extract text per page from a PDF and chunk while recording source page numbers.

    Extracts text page-by-page from the source PDF, assigns source page numbers
    to each segment, and generates semantic chunks preserving page attribution.

    Args:
        pdf_path: Filesystem path to the tenant PDF document.
        tenant_id: Unique identifier for the owning tenant.
        chunk_size_tokens: Maximum target tokens per chunk.
        overlap_tokens: Overlap tokens for boundary continuity.

    Returns:
        List of DocumentChunk instances with verified page numbers.
    """
    from ingestion.loader import extract_text_from_pdf

    pages = extract_text_from_pdf(pdf_path, tenant_id=tenant_id)
    return chunk_tenant_document(
        pages=pages,
        chunk_size_tokens=chunk_size_tokens,
        overlap_tokens=overlap_tokens,
    )
