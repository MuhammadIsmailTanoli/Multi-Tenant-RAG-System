# Multi-Tenant RAG System

A production-grade Retrieval-Augmented Generation (RAG) backend engineered for strict multi-tenant data isolation, zero cross-tenant contamination, and enterprise-grade query routing.

---

## Project Overview

This system manages document corpora across distinct corporate entities (Acme Corp and Globex Corporation) with strict tenant segregation. Rather than relying on fragile prompt instructions or error-prone metadata filtering on a shared vector store, each tenant is granted an isolated vector index and storage partition.

### Key Architectural Pillars

- Physical Tenant Partitioning: Each tenant handbook is parsed, chunked, embedded, and stored in an isolated collection and storage path.
- Guaranteed Zero Leakage: Cross-company contamination is prevented by architectural boundary enforcement and post-retrieval validation.
- Extensible Tenant Registry: Centralized tenant management enables onboarding additional clients without modifying core pipeline code.
- Grounded Answers with Citations: Responses are strictly synthesized from retrieved context with specific section and page attribution.
- Defensive Prompt Engineering: Resilient against prompt injection and context escape attempts.
- Automated Verification: Rigorous automated test suite proving strict data segregation and error handling.

---

## Repository Structure

```text
multi-tenant-rag-system/
├── data/
│   └── handbooks/               # Raw PDF handbooks (Acme and Globex)
├── ingestion/                   # Document parsing, chunking, and embedding pipeline
│   └── __init__.py
├── api/                         # FastAPI backend, routing, and query service
│   └── __init__.py
├── tests/                       # Test suite (unit, isolation, and integration tests)
│   └── __init__.py
├── .env.example                 # Environment configuration template
├── .gitignore                   # Git ignore rules (Python, env, vector storage)
├── requirements.txt             # Project dependencies
├── Architecture Pipeline.svg    # End-to-end architecture diagram
└── README.md                    # Project documentation and execution guide
```

---

## Quick Start (Preview)

### 1. Environment Setup

```bash
# Clone the repository and navigate into the folder
cd Multi-Tenant-RAG-System

# Create and activate virtual environment
python -m venv venv

# On Windows:
.\venv\Scripts\activate

# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
```

### 2. Ingestion and Execution

- Ingestion: Ingest client handbooks into isolated vector partitions.
- API Server: Run the FastAPI service on http://localhost:8000.
- Testing: Run pytest to verify complete tenant isolation.
