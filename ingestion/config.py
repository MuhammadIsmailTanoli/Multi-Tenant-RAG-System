"""Configuration module for multi-tenant ingestion and system settings.

Loads and validates tenants.yaml ensuring distinct vector collections,
valid file paths, and strict isolation parameters for every tenant.
"""

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
import re
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TENANTS_PATH = PROJECT_ROOT / "tenants.yaml"


class TenantConfig(BaseModel):
    """Configuration definition for an individual tenant."""

    id: str = Field(
        ...,
        description="Unique identifier for the tenant, strictly lowercase alphanumeric.",
    )
    name: str = Field(..., description="Display name of the tenant organization.")
    pdf_path: str = Field(
        ...,
        description="Path to the tenant source PDF handbook relative to project root.",
    )
    collection_name: str = Field(
        ...,
        description="Chroma vector database collection name dedicated to this tenant.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional tenant description or domain context.",
    )

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        clean_id = v.strip().lower()
        if not re.match(r"^[a-z0-9_-]+$", clean_id):
            raise ValueError(
                f"Invalid tenant ID '{v}'. Tenant IDs must only contain lowercase alphanumeric characters, hyphens, and underscores."
            )
        return clean_id

    @field_validator("collection_name")
    @classmethod
    def validate_collection_name(cls, v: str) -> str:
        clean_name = v.strip()
        # Chroma collection naming rules: 3-63 characters, alphanumeric, underscores, hyphens
        if not (3 <= len(clean_name) <= 63):
            raise ValueError(
                f"Collection name '{clean_name}' must be between 3 and 63 characters long."
            )
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$", clean_name):
            raise ValueError(
                f"Collection name '{clean_name}' contains invalid characters or does not start/end with an alphanumeric character."
            )
        return clean_name

    @property
    def resolved_pdf_path(self) -> Path:
        """Resolve the source PDF path relative to the project root."""
        p = Path(self.pdf_path)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        return p

    def validate_file_exists(self) -> None:
        """Validate that the configured PDF file actually exists on the filesystem."""
        path = self.resolved_pdf_path
        if not path.is_file():
            raise FileNotFoundError(
                f"Handbook file for tenant '{self.id}' not found at: {path}"
            )


class TenantsFileSchema(BaseModel):
    """Schema wrapper for the list of tenants in tenants.yaml."""

    tenants: List[TenantConfig]

    @model_validator(mode="after")
    def check_uniqueness(self) -> "TenantsFileSchema":
        seen_ids = set()
        seen_collections = set()

        for tenant in self.tenants:
            if tenant.id in seen_ids:
                raise ValueError(
                    f"Duplicate tenant ID detected: '{tenant.id}'. Tenant IDs must be strictly unique."
                )
            seen_ids.add(tenant.id)

            if tenant.collection_name in seen_collections:
                raise ValueError(
                    f"Duplicate collection name detected: '{tenant.collection_name}'. "
                    f"Each tenant must have an isolated collection."
                )
            seen_collections.add(tenant.collection_name)

        return self


class Settings(BaseSettings):
    """Application-wide environment settings."""

    openai_api_key: Optional[str] = Field(
        default=None,
        description="API Key for OpenAI embeddings and completions.",
    )
    embedding_model: str = Field(
        default="Qwen/Qwen3-Embedding-0.6B",
        description="Embedding model name for vector representations.",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="LLM model name for grounded answer generation.",
    )
    llm_temperature: float = Field(
        default=0.0,
        description="Sampling temperature for deterministic generation.",
    )
    chroma_persist_directory: str = Field(
        default="./data/chroma",
        description="Directory path for persistent vector storage.",
    )
    api_host: str = Field(default="0.0.0.0", description="API server host.")
    api_port: int = Field(default=8000, description="API server port.")
    log_level: str = Field(default="INFO", description="Logging verbosity level.")

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_chroma_dir(self) -> Path:
        """Resolve the persistent Chroma storage directory relative to project root."""
        p = Path(self.chroma_persist_directory)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        return p

    def get_tenant_storage_path(self, tenant_id: str) -> Path:
        """Return dedicated storage path for a tenant to enforce directory-level physical isolation."""
        clean_id = tenant_id.strip().lower()
        return self.resolved_chroma_dir / clean_id


def load_tenants_config(
    config_path: Optional[Path | str] = None,
    verify_files: bool = False,
) -> Dict[str, TenantConfig]:
    """Load, parse, and validate tenant configurations from YAML.

    Args:
        config_path: Optional custom path to tenants.yaml. Defaults to project root.
        verify_files: If True, checks that source PDF files exist on disk.

    Returns:
        Dictionary mapping tenant ID to TenantConfig.

    Raises:
        FileNotFoundError: If configuration file is missing or PDF is missing with verify_files=True.
        ValueError: If configuration syntax or schema validation fails.
    """
    path = Path(config_path) if config_path else DEFAULT_TENANTS_PATH
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Tenant configuration file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            raw_data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML parsing error in {path}: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError(
            f"Invalid format in {path}: root object must be a YAML mapping."
        )

    validated_schema = TenantsFileSchema.model_validate(raw_data)
    tenant_map: Dict[str, TenantConfig] = {}

    for tenant in validated_schema.tenants:
        if verify_files:
            tenant.validate_file_exists()
        tenant_map[tenant.id] = tenant

    return tenant_map


def get_tenant(
    tenant_id: str,
    config_path: Optional[Path | str] = None,
    verify_files: bool = False,
) -> TenantConfig:
    """Retrieve configuration for a specific tenant by ID.

    Args:
        tenant_id: Unique tenant identifier (e.g., 'acme', 'globex').
        config_path: Optional path to configuration file.
        verify_files: If True, verifies source PDF existence.

    Returns:
        TenantConfig instance for the requested tenant.

    Raises:
        ValueError: If tenant_id is unknown or invalid.
    """
    clean_id = tenant_id.strip().lower()
    tenants = load_tenants_config(config_path=config_path, verify_files=verify_files)
    if clean_id not in tenants:
        valid_options = ", ".join(sorted(tenants.keys()))
        raise ValueError(
            f"Unknown tenant '{tenant_id}'. Available configured tenants: [{valid_options}]"
        )
    return tenants[clean_id]


def list_tenants(config_path: Optional[Path | str] = None) -> List[str]:
    """Return a list of all configured tenant IDs."""
    tenants = load_tenants_config(config_path=config_path)
    return sorted(list(tenants.keys()))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor for application settings."""
    return Settings()
