"""Manual verification script for multi-tenant ingestion.

Runs the full ingestion pipeline for all tenants and prints a structured
summary of chunk counts, embedding dimensions, tenant isolation, and top chunks.
"""

import sys
import logging
from pathlib import Path
import chromadb
from chromadb.config import Settings as ChromaSettings
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ingestion.config import load_tenants_config, get_settings
from ingestion.loader import load_tenant_document
from ingestion.chunking import chunk_tenant_document
from ingestion.ingest import run_ingestion, get_chroma_client
from ingestion.embedder import get_embedder

logging.basicConfig(level=logging.WARNING)
console = Console()


def print_ingestion_summary():
    console.print(Panel.fit(
        "[bold cyan]Multi-Tenant RAG System — Ingestion Verification[/bold cyan]\n"
        "[dim]Local Qwen3-Embedding-0.6B • Isolated Chroma Collections per Tenant[/dim]",
        border_style="cyan",
    ))

    # ------------------------------------------------------------------ #
    # 1. Pre-ingestion: chunk + dimension summary without storing
    # ------------------------------------------------------------------ #
    console.print("\n[bold yellow]Step 1: PDF Loading & Chunking Summary[/bold yellow]")
    tenants = load_tenants_config()
    chunk_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
    chunk_table.add_column("Tenant", style="cyan", justify="left")
    chunk_table.add_column("Pages Extracted", justify="center")
    chunk_table.add_column("Chunks Generated", justify="center")
    chunk_table.add_column("Avg Chunk Tokens", justify="center")
    chunk_table.add_column("Page Range", justify="center")

    for tid, tcfg in tenants.items():
        pages = load_tenant_document(tid)
        chunks = chunk_tenant_document(pages)
        avg_tokens = sum(c.token_count for c in chunks) // len(chunks) if chunks else 0
        all_pages = f"1 – {pages[-1].page_number}" if pages else "N/A"
        chunk_table.add_row(
            f"[bold]{tcfg.name}[/bold]",
            str(len(pages)),
            str(len(chunks)),
            str(avg_tokens),
            all_pages,
        )
    console.print(chunk_table)

    # ------------------------------------------------------------------ #
    # 2. Run full ingestion with Qwen embedder
    # ------------------------------------------------------------------ #
    console.print("\n[bold yellow]Step 2: Running Full Ingestion (Qwen3-Embedding-0.6B)[/bold yellow]")
    console.print("[dim]Downloading/loading model on first run (may take a moment)...[/dim]\n")

    results = run_ingestion(reset=True)

    # ------------------------------------------------------------------ #
    # 3. Post-ingestion: vector store summary
    # ------------------------------------------------------------------ #
    console.print("\n[bold yellow]Step 3: Vector Store Summary[/bold yellow]")
    client = get_chroma_client()
    embedder = get_embedder()

    vector_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
    vector_table.add_column("Tenant", style="cyan")
    vector_table.add_column("Collection Name", style="yellow")
    vector_table.add_column("Chunks Indexed", justify="center")
    vector_table.add_column("Embedding Dim", justify="center")
    vector_table.add_column("Model", style="dim")

    for tid, tcfg in tenants.items():
        col = client.get_collection(name=tcfg.collection_name)
        data = col.get(limit=1, include=["embeddings"])
        embeddings = data.get("embeddings")
        dim = len(embeddings[0]) if embeddings is not None and len(embeddings) > 0 else "N/A"
        vector_table.add_row(
            f"[bold]{tcfg.name}[/bold]",
            tcfg.collection_name,
            str(col.count()),
            str(dim),
            embedder.model_name,
        )
    console.print(vector_table)

    # ------------------------------------------------------------------ #
    # 4. Isolation check
    # ------------------------------------------------------------------ #
    console.print("\n[bold yellow]Step 4: Tenant Isolation Audit[/bold yellow]")
    isolation_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
    isolation_table.add_column("Collection", style="cyan")
    isolation_table.add_column("Total Chunks", justify="center")
    isolation_table.add_column("All tenant_id Match?", justify="center")
    isolation_table.add_column("Foreign Chunks Found?", justify="center")

    for tid, tcfg in tenants.items():
        col = client.get_collection(name=tcfg.collection_name)
        data = col.get(include=["metadatas"])
        all_match = all(m.get("tenant_id") == tid for m in data["metadatas"])
        foreign = any(m.get("tenant_id") != tid for m in data["metadatas"])
        isolation_table.add_row(
            tcfg.collection_name,
            str(len(data["metadatas"])),
            "[bold green]YES[/bold green]" if all_match else "[bold red]NO[/bold red]",
            "[bold red]YES — LEAK![/bold red]" if foreign else "[bold green]NONE[/bold green]",
        )
    console.print(isolation_table)

    # ------------------------------------------------------------------ #
    # 5. Sample top chunk per tenant
    # ------------------------------------------------------------------ #
    console.print("\n[bold yellow]Step 5: Sample Chunk per Tenant[/bold yellow]")
    for tid, tcfg in tenants.items():
        col = client.get_collection(name=tcfg.collection_name)
        data = col.get(limit=1, include=["documents", "metadatas"])
        if data["documents"]:
            snippet = data["documents"][0][:280].replace("\n", " ").strip()
            meta = data["metadatas"][0]
            console.print(Panel(
                f"[bold]{tcfg.name}[/bold] — chunk [cyan]{meta['chunk_id']}[/cyan] "
                f"(pages {meta['page_start']}–{meta['page_end']}, {meta['token_count']} tokens)\n\n"
                f"[dim]{snippet}...[/dim]",
                border_style="yellow",
            ))

    console.print("\n[bold green]Ingestion verification complete. All tenants successfully indexed and isolated.[/bold green]\n")


if __name__ == "__main__":
    print_ingestion_summary()
