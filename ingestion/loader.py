"""PDF document extraction and loading module.

Utilizes pypdf to extract page-level text and metadata from tenant handbooks,
ensuring consistent structure and strict tenant association from the start.
"""

from pathlib import Path
from typing import Dict, List, Optional
import re
import logging
from pydantic import BaseModel, Field
import pypdf

from ingestion.config import get_tenant, TenantConfig

logger = logging.getLogger(__name__)


class DocumentPage(BaseModel):
    """Represents a single parsed page from a tenant PDF document."""

    tenant_id: str = Field(..., description="Tenant identifier owning this document page.")
    source_file: str = Field(..., description="Filename or relative path of the source PDF.")
    page_number: int = Field(..., description="1-indexed page number within the document.")
    total_pages: int = Field(..., description="Total page count of the source document.")
    text: str = Field(..., description="Extracted and normalized text content of the page.")
    metadata: Dict[str, str | int] = Field(
        default_factory=dict,
        description="Supplemental page-level metadata (e.g., headers, dimensions).",
    )


def clean_page_text(raw_text: str) -> str:
    """Normalize and sanitize extracted PDF text.

    - Replaces null bytes and non-printable control characters.
    - Standardizes CRLF and CR to LF line endings.
    - Normalizes excessive whitespace and runs of blank lines while preserving paragraphs.
    - Strips leading and trailing whitespace.
    """
    if not raw_text:
        return ""

    # Remove null characters and non-printable control chars except newlines and tabs
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw_text)

    # Standardize line breaks
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Replace runs of horizontal whitespace (spaces, tabs) with a single space
    text = re.sub(r"[ \t]+", " ", text)

    # Replace runs of 3+ consecutive newlines with 2 newlines (paragraph break)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def extract_text_from_pdf(
    pdf_path: Path | str,
    tenant_id: str,
) -> List[DocumentPage]:
    """Extract page-level text and metadata from a PDF file.

    Args:
        pdf_path: Filesystem path to the PDF document.
        tenant_id: Tenant identifier associated with this document.

    Returns:
        List of DocumentPage instances containing normalized text and page numbers.

    Raises:
        FileNotFoundError: If the specified PDF file cannot be located.
        ValueError: If the file is empty or cannot be parsed as a valid PDF.
    """
    path = Path(pdf_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found at path: {path}")

    try:
        reader = pypdf.PdfReader(str(path))
    except Exception as exc:
        raise ValueError(f"Failed to read PDF file '{path.name}': {exc}") from exc

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError(f"PDF file '{path.name}' contains no readable pages.")

    pages: List[DocumentPage] = []

    for idx, page in enumerate(reader.pages):
        page_number = idx + 1
        try:
            raw_text = page.extract_text() or ""
        except Exception as exc:
            logger.warning(
                "Error extracting text from page %d of '%s': %s",
                page_number,
                path.name,
                exc,
            )
            raw_text = ""

        cleaned = clean_page_text(raw_text)

        pages.append(
            DocumentPage(
                tenant_id=tenant_id.strip().lower(),
                source_file=path.name,
                page_number=page_number,
                total_pages=total_pages,
                text=cleaned,
                metadata={
                    "tenant_id": tenant_id.strip().lower(),
                    "source_file": path.name,
                    "page_number": page_number,
                    "total_pages": total_pages,
                    "character_count": len(cleaned),
                },
            )
        )

    logger.info(
        "Successfully extracted %d pages for tenant '%s' from '%s'.",
        len(pages),
        tenant_id,
        path.name,
    )
    return pages


def load_tenant_document(
    tenant_id: str,
    config_path: Optional[Path | str] = None,
) -> List[DocumentPage]:
    """Helper to load handbook pages directly using tenant configuration registry.

    Args:
        tenant_id: Identifier of the tenant (e.g., 'acme', 'globex').
        config_path: Optional path to custom tenants.yaml configuration.

    Returns:
        List of DocumentPage objects for the tenant.
    """
    tenant_cfg: TenantConfig = get_tenant(tenant_id, config_path=config_path, verify_files=True)
    return extract_text_from_pdf(
        pdf_path=tenant_cfg.resolved_pdf_path,
        tenant_id=tenant_cfg.id,
    )
