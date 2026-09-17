"""
Script to generate a professional, clean 3-page engineering specification
and architecture documentation PDF for the Multi-Tenant RAG System.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas
import pypdf

class NumberedCanvas(canvas.Canvas):
    """Canvas that performs two passes to dynamically compute and render total page count."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (pages 2 and 3)
        if self._pageNumber > 1:
            self.drawString(54, 752, "MULTI-TENANT RAG SYSTEM — TECHNICAL SPECIFICATION & ARCHITECTURE")
            self.drawRightString(558, 752, "SEPTEMBER 2026")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(54, 746, 558, 746)

        # Footer (all pages)
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 42, 558, 42)
        
        self.drawString(54, 30, "Confidential — Architecture & Implementation Reference")
        page_text = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(558, 30, page_text)
        self.restoreState()


def build_pdf(filename="documentation.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4,
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=10,
        spaceAfter=6,
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=6,
        spaceAfter=3,
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=5,
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.2,
        leading=11,
        textColor=colors.HexColor("#334155"),
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3,
    )

    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=10,
        textColor=colors.HexColor("#1E293B"),
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.8,
        leading=10,
        textColor=colors.HexColor("#0F172A"),
    )

    table_cell_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#FFFFFF"),
    )

    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.2,
        leading=11.5,
        textColor=colors.HexColor("#1E3A8A"),
    )

    story = []

    # =========================================================================
    # PAGE 1: SYSTEM OVERVIEW & ARCHITECTURE
    # =========================================================================
    story.append(Paragraph("Multi-Tenant RAG System", title_style))
    story.append(Paragraph("System Architecture, Security Isolation, and Implementation Specification &bull; <b>Author:</b> Muhammad Ismail Tanoli", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=10))

    # 1. Executive Summary
    story.append(Paragraph("1. Executive Summary & Design Philosophy", h1_style))
    story.append(Paragraph(
        "Standard multi-tenant Retrieval-Augmented Generation (RAG) architectures frequently ingest documents from "
        "multiple organizations into a unified vector index, segregating records using soft metadata tags (e.g. "
        "<code>tenant_id: acme</code>). In production environments, this poses significant security and compliance vulnerabilities: "
        "improper filtering, vector index leakage, or adversarial prompt injections can expose confidential corporate data across tenants. "
        "This project implements <b>strict physical multi-tenancy</b> with separate vector database instances per organization, dual-factor "
        "authentication (Company credentials + Google OAuth 2.0 verification), persistent identity-keyed rate limiting, and an optimized small-talk filter.",
        body_style
    ))

    # 2. Technology Matrix
    story.append(Paragraph("2. Technical Stack & Component Specification", h1_style))
    
    tech_data = [
        [Paragraph("Subsystem", table_cell_header), Paragraph("Technology / Model", table_cell_header), Paragraph("Key Functional Role", table_cell_header)],
        [Paragraph("<b>Frontend</b>", table_cell_bold), Paragraph("React 18, TypeScript, Vite, Tailwind CSS", table_cell), Paragraph("Responsive dark glassmorphism UI, real-time quota gauges, 500-char input limiter.", table_cell)],
        [Paragraph("<b>Backend API</b>", table_cell_bold), Paragraph("FastAPI (Python 3.13), Pydantic v2, Uvicorn", table_cell), Paragraph("Asynchronous REST service, route-level authorization, custom CORS and security handlers.", table_cell)],
        [Paragraph("<b>Vector Storage</b>", table_cell_bold), Paragraph("ChromaDB (Isolated physical collections)", table_cell), Paragraph("Separate disk persistence per tenant (<code>tenant_acme</code> vs <code>tenant_globex</code>).", table_cell)],
        [Paragraph("<b>Embeddings</b>", table_cell_bold), Paragraph("<code>all-MiniLM-L6-v2</code> (Sentence-Transformers)", table_cell), Paragraph("384-dimensional dense semantic vectors with Cosine Similarity index.", table_cell)],
        [Paragraph("<b>LLM Inference</b>", table_cell_bold), Paragraph("Groq (LLaMA 3.3 70B Versatile)", table_cell), Paragraph("Sub-second grounded response synthesis constrained strictly to tenant context.", table_cell)],
        [Paragraph("<b>Identity & Auth</b>", table_cell_bold), Paragraph("Google OAuth 2.0 + PyJWT + Passlib (bcrypt)", table_cell), Paragraph("Dual-factor authentication, cryptographic verification of Google ID token claims.", table_cell)],
        [Paragraph("<b>Rate Limiting</b>", table_cell_bold), Paragraph("SlowAPI + Custom SQLite Storage", table_cell), Paragraph("Persistent sliding-window counters keyed by permanent user Google ID (<code>google_sub</code>).", table_cell)],
    ]

    t_tech = Table(tech_data, colWidths=[85, 175, 244])
    t_tech.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_tech)
    story.append(Spacer(1, 8))

    # 3. System Flow of Control
    story.append(Paragraph("3. End-to-End System Flow of Control", h1_style))
    story.append(Paragraph(
        "The system enforces a deterministic, multi-stage pipeline for every incoming user request:",
        body_style
    ))

    flow_items = [
        "<b>Phase 1 &mdash; Tenant Selection & Credentials Check:</b> The user selects Acme Corp or Globex Corporation and enters the company password. Passwords are cryptographically validated against pre-hashed bcrypt secrets stored in <code>tenants.yaml</code>.",
        "<b>Phase 2 &mdash; Google Identity Verification:</b> The browser completes Google OAuth 2.0. The backend verifies the Google ID token signature against Google's public JWKS certificates and extracts the immutable subject identifier (<code>google_sub</code>).",
        "<b>Phase 3 &mdash; Scoped JWT Session Issuance:</b> FastAPI signs a JWT access token embedding <code>tenant_id</code>, <code>google_sub</code>, and email. The token expires in 60 minutes and is maintained in client-side memory state.",
        "<b>Phase 4 &mdash; Fast Tenant Switching:</b> Users moving between organizations supply the new company password alongside their active Google token. The backend verifies tenant access and reissues a scoped token without redundant Google logins.",
        "<b>Phase 5 &mdash; Guardrails & Retrieval:</b> Inbound queries pass through the 500-character validator, small-talk filter (bypassing vector search for greetings), and identity-keyed SQLite rate limiter before querying the tenant's isolated ChromaDB database.",
        "<b>Phase 6 &mdash; Grounded Synthesis:</b> Retrieved text chunks populate a hardened system prompt. Groq LLaMA 3.3 synthesizes a concise, factual answer with raw file paths and leaky citations completely stripped."
    ]
    for item in flow_items:
        story.append(Paragraph(f"&bull; {item}", bullet_style))

    # Force PageBreak to start Page 2
    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: SECURITY ISOLATION & RATE LIMITING MECHANICS
    # =========================================================================
    story.append(Paragraph("4. Multi-Tenant Physical Isolation Architecture", h1_style))
    story.append(Paragraph(
        "To guarantee zero cross-tenant contamination, the application implements physical data partitioning rather than virtual logical tagging:",
        body_style
    ))

    isolation_box = [
        [Paragraph(
            "<b>Physical Directory Partitioning:</b><br/>"
            "&bull; Acme Corp Collection: <code>data/chroma/tenant_acme</code> (indexed from Acme Corp Employee Handbook.pdf)<br/>"
            "&bull; Globex Corporation Collection: <code>data/chroma/tenant_globex</code> (indexed from Globex Corporation Employee Handbook.pdf)<br/>"
            "&bull; Separate Persistent Clients: Separate ChromaDB client connections prevent cross-collection querying in memory.",
            callout_style
        )]
    ]
    t_iso = Table(isolation_box, colWidths=[504])
    t_iso.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#3B82F6")),
    ]))
    story.append(t_iso)
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "<b>Cryptographic Route Enforcement:</b> At the API layer (<code>POST /query</code>), the route handler checks that the <code>tenant_id</code> in the payload exactly matches the <code>tenant_id</code> signed into the verified JWT token. If an Acme user attempts to query the Globex handbook, the backend immediately terminates the request with <code>HTTP 403 Forbidden</code> before initiating vector retrieval.",
        body_style
    ))

    # 5. Persistent Identity-Keyed Rate Limiting
    story.append(Paragraph("5. Persistent Identity-Keyed Rate Limiting", h1_style))
    story.append(Paragraph(
        "Most rate limiters track requests by IP address (easily spoofed or shared by multiple users in an office) "
        "or by company session (allowing a user to bypass quotas by switching between Acme and Globex). "
        "This system implements a <b>Google Subject-Keyed Quota Engine</b>:",
        body_style
    ))

    quota_data = [
        [Paragraph("Quota Window", table_cell_header), Paragraph("Limit Threshold", table_cell_header), Paragraph("Keying Identifier", table_cell_header), Paragraph("Persistence Layer", table_cell_header)],
        [Paragraph("<b>Daily Window</b>", table_cell_bold), Paragraph("50 queries / 24 hours", table_cell), Paragraph("<code>google_user:{google_sub}</code>", table_cell), Paragraph("SQLite (<code>rate_limits.db</code>)", table_cell)],
        [Paragraph("<b>Weekly Window</b>", table_cell_bold), Paragraph("200 queries / 7 days", table_cell), Paragraph("<code>google_user:{google_sub}</code>", table_cell), Paragraph("SQLite (<code>rate_limits.db</code>)", table_cell)],
    ]
    t_quota = Table(quota_data, colWidths=[100, 120, 144, 140])
    t_quota.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_quota)
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        "<b>Storage Implementation:</b> SlowAPI is paired with a custom SQLite storage engine with write-ahead synchronization. "
        "Counters persist across backend server restarts and ngrok tunnel refreshes. "
        "When an authenticated user makes 30 queries under Acme Corp and 20 under Globex Corporation, their daily quota is exhausted. "
        "Further queries trigger an immediate <code>HTTP 429 Too Many Requests</code> with an RFC-compliant <code>Retry-After</code> header.",
        body_style
    ))

    # 6. Real-Time Quota Interface & Takeover Modal
    story.append(Paragraph("6. Real-Time Quota Monitoring & HTTP 429 Takeover", h1_style))
    story.append(Paragraph(
        "The frontend synchronizes rate limit status through two complementary components:",
        body_style
    ))
    story.append(Paragraph(
        "&bull; <b>Usage Modal (<code>GET /limits</code>):</b> Accessible from the navigation bar. Displays live daily and weekly progress meters, color-coded based on consumption (Emerald &lt;60%, Amber 60%&ndash;85%, Rose &gt;85%), with exact remaining query counts and window reset timestamps.",
        bullet_style
    ))
    story.append(Paragraph(
        "&bull; <b>HTTP 429 Takeover Screen:</b> Upon receiving a rate-limit exception, the chat UI triggers a full-screen takeover modal. The modal displays the exhausted tier, remaining cooldown period in seconds, and an animated countdown timer.",
        bullet_style
    ))

    # Force PageBreak to start Page 3
    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: OPTIMIZATIONS, EDGE CASES, TESTING & DEPLOYMENT
    # =========================================================================
    story.append(Paragraph("7. Edge-Case Hardening & Cost Optimizations", h1_style))

    story.append(Paragraph("A. Small-Talk Interceptor (Compute & Cost Optimization)", h2_style))
    story.append(Paragraph(
        "Conversational inquiries (e.g. <i>'hi', 'hello', 'good morning', 'hey'</i>) do not require semantic embedding computation "
        "or retrieval from company handbooks. An optimized regular expression interceptor catches small-talk in <b>&lt;1 ms</b>, returning "
        "a polite guidance prompt immediately. This eliminates unnecessary vector database reads and saves valuable LLM context tokens.",
        body_style
    ))

    story.append(Paragraph("B. Character Limit & Client/Server Input Guardrails", h2_style))
    story.append(Paragraph(
        "To mitigate prompt injection attacks, buffer exploitation, and runaway LLM costs, input queries are strictly validated: "
        "the frontend enforces a real-time 500-character counter with visual threshold alerts, while the backend Pydantic schema "
        "rejects empty messages, whitespace padding, or queries exceeding 500 characters with <code>HTTP 422 Unprocessable Entity</code>.",
        body_style
    ))

    story.append(Paragraph("C. Production ngrok Header Injection", h2_style))
    story.append(Paragraph(
        "Free ngrok tunnels present an HTML interstitial warning page on first contact, corrupting automated API requests. "
        "All frontend API calls inject <code>ngrok-skip-browser-warning: true</code> across headers, guaranteeing smooth JSON serialization across the tunnel.",
        body_style
    ))

    # 8. Automated Verification & Test Suite
    story.append(Paragraph("8. Automated Testing & Verification Suite", h1_style))
    story.append(Paragraph(
        "The repository contains an exhaustive automated test suite comprising <b>121 unit and integration tests</b> executed via <code>pytest</code>:",
        body_style
    ))

    test_data = [
        [Paragraph("Test Module", table_cell_header), Paragraph("Scope of Verification", table_cell_header)],
        [Paragraph("<code>test_isolation.py</code>", table_cell_bold), Paragraph("Verifies physical collection segregation, cross-tenant rejection, and prompt injection containment.", table_cell)],
        [Paragraph("<code>test_auth_rate_limit_flow.py</code>", table_cell_bold), Paragraph("Full OAuth lifecycle, bcrypt verification, company switching, and 50/day SQLite limit enforcement.", table_cell)],
        [Paragraph("<code>test_api.py</code>", table_cell_bold), Paragraph("FastAPI endpoints, Pydantic input validation, CORS headers, and standard HTTP error codes.", table_cell)],
        [Paragraph("<code>test_ingestion.py</code>", table_cell_bold), Paragraph("PDF extraction fidelity, chunking boundaries, metadata tagging, and ChromaDB vector generation.", table_cell)],
        [Paragraph("<code>test_retriever.py</code>", table_cell_bold), Paragraph("Semantic similarity search scoring, top-k chunk ranking, and tenant collection boundaries.", table_cell)],
        [Paragraph("<code>test_llm_provider.py</code>", table_cell_bold), Paragraph("Groq LLaMA 3.3, Gemini, and Claude adapter functionality and fallback error handling.", table_cell)],
    ]
    t_test = Table(test_data, colWidths=[140, 364])
    t_test.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#FFFFFF"), colors.HexColor("#F8FAFC")]),
    ]))
    story.append(t_test)
    story.append(Spacer(1, 8))

    # 9. Deployment Topology & Live Demo
    story.append(Paragraph("9. Deployment Topology & Live Evaluation", h1_style))
    story.append(Paragraph(
        "<b>Cloud Frontend:</b> Hosted on Vercel with automatic global edge delivery: "
        "<b><font color='#2563EB'><u>https://multi-tenant-rag-system.vercel.app</u></font></b>.<br/>"
        "<b>Hybrid Private Backend:</b> Hosted on private infrastructure and connected via secure TLS tunnel (ngrok). "
        "For live evaluation, please message <b>WhatsApp: +92 313 5060949</b> 10 minutes prior to activate the tunnel.<br/>"
        "<b>Demo Passwords:</b> Acme Corp: <code>Acme@Admin</code> &bull; Globex Corporation: <code>Globex@Admin</code> (Requires Google OAuth Sign-in).",
        body_style
    ))

    # Build PDF using NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    
    # Check page count
    reader = pypdf.PdfReader(filename)
    page_count = len(reader.pages)
    print(f"Generated '{filename}' successfully with {page_count} pages.")
    return page_count

if __name__ == "__main__":
    build_pdf()
