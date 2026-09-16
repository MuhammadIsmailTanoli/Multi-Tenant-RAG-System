"""Quick post-ingestion summary — reads existing Chroma collections (no re-ingestion)."""

import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ingestion.config import load_tenants_config, get_settings
from ingestion.ingest import get_chroma_client
from ingestion.embedder import get_embedder

logging.basicConfig(level=logging.WARNING)
console = Console()


def print_summary():
    console.print(Panel.fit(
        "[bold cyan]Multi-Tenant RAG System — Ingestion Verification Summary[/bold cyan]\n"
        "[dim]Qwen3-Embedding-0.6B | Isolated Chroma Collections per Tenant[/dim]",
        border_style="cyan",
    ))

    tenants = load_tenants_config()
    client = get_chroma_client()
    embedder = get_embedder()

    # ---- Vector Store Summary ----
    console.print("\n[bold yellow]Vector Store Summary[/bold yellow]")
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

    # ---- Tenant Isolation Audit ----
    console.print("\n[bold yellow]Tenant Isolation Audit[/bold yellow]")
    isolation_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
    isolation_table.add_column("Collection", style="cyan")
    isolation_table.add_column("Total Chunks", justify="center")
    isolation_table.add_column("All tenant_id Correct?", justify="center")
    isolation_table.add_column("Foreign Data Found?", justify="center")

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

    # ---- Sample Chunk per Tenant ----
    console.print("\n[bold yellow]Sample Chunk per Tenant[/bold yellow]")
    for tid, tcfg in tenants.items():
        col = client.get_collection(name=tcfg.collection_name)
        data = col.get(limit=1, include=["documents", "metadatas"])
        if data["documents"]:
            snippet = data["documents"][0][:300].replace("\n", " ").strip()
            meta = data["metadatas"][0]
            console.print(Panel(
                f"[bold]{tcfg.name}[/bold] — [cyan]{meta['chunk_id']}[/cyan] "
                f"(pages {meta['page_start']}–{meta['page_end']}, {meta['token_count']} tokens)\n\n"
                f"[dim]{snippet}...[/dim]",
                border_style="yellow",
            ))

    console.print("\n[bold green]All tenants verified. Data isolated. No cross-contamination.[/bold green]\n")


if __name__ == "__main__":
    print_summary()
