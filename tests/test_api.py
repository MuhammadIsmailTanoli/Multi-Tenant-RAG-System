"""Unit and integration tests for FastAPI query endpoints.

Verifies:
1. POST /auth/company authenticates tenant password and returns scoped JWT.
2. POST /query requires Bearer token authentication (401 for missing/invalid/expired).
3. POST /query enforces tenant scope matching (403 for cross-tenant tokens).
4. POST /query validates tenant_id against tenants.yaml (422 for unknown).
5. POST /query validates question content, length, and control characters (422).
6. Small-talk queries bypass Chroma retrieval and LLM context calls.
7. Static document serving and system health endpoints work as expected.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.auth import create_tenant_token

client = TestClient(app)


def get_auth_headers(tenant_id: str = "acme") -> dict:
    """Generate Authorization headers with a valid signed JWT scoped to tenant_id."""
    token = create_tenant_token(tenant_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def mock_llm_adapter_for_tests():
    """Mock LLM adapter to ensure tests execute offline deterministically and without quota limits."""
    mock_adapter = MagicMock()
    mock_adapter.provider_name = "mock-provider"
    mock_adapter.model_name = "mock-model"
    mock_adapter.generate_answer.return_value = "Mock answer grounded in handbook policies."
    with patch("api.main.get_llm_adapter", return_value=mock_adapter):
        yield mock_adapter


@pytest.fixture(autouse=True)
def mock_retriever_for_tests():
    """Mock vector retriever to ensure API tests execute offline instantaneously without loading Qwen embedding weights."""
    from api.retriever import RetrievedChunk

    def _mock_retrieve(tenant_id: str, question: str, top_k: int = 4, **kwargs):
        return [
            RetrievedChunk(
                chunk_id=f"{tenant_id}_chunk_0",
                text=f"Official handbook policy regarding {question}.",
                tenant_id=tenant_id,
                source_file=f"{tenant_id.capitalize()} Employee Handbook.pdf",
                page_start=1,
                page_end=2,
                chunk_index=0,
                token_count=80,
                distance=0.1,
                similarity=0.9,
            )
        ]

    with patch("api.main.retrieve_tenant_chunks", side_effect=_mock_retrieve) as mock_retriever:
        yield mock_retriever


# ---------------------------------------------------------------------------
# System & Health Endpoints
# ---------------------------------------------------------------------------

def test_health_check():
    """Verify that the health check endpoint returns 200 and active tenants."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["active_tenants_count"] >= 2
    assert "acme" in data["tenants"]
    assert "globex" in data["tenants"]


def test_list_registered_tenants():
    """Verify that GET /tenants lists all configured tenants."""
    response = client.get("/tenants")
    assert response.status_code == 200
    tenants = response.json()
    assert len(tenants) >= 2
    tenant_ids = [t["id"] for t in tenants]
    assert "acme" in tenant_ids
    assert "globex" in tenant_ids


def test_root_endpoint_metadata():
    """Verify root endpoint advertises available endpoints including /documents and /auth."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "auth" in data["endpoints"]
    assert "documents" in data["endpoints"]
    assert "/documents/{filename}" in data["endpoints"]["documents"]


# ---------------------------------------------------------------------------
# Company Password Authentication & Unified Session Flow (/auth/company, /auth/switch-company)
# ---------------------------------------------------------------------------

MOCK_GOOGLE_ID_INFO = {
    "sub": "google-user-1234567890",
    "email": "developer@example.com",
    "email_verified": True,
    "name": "Alex Smith",
    "picture": "https://lh3.googleusercontent.com/a/test-avatar",
}


def test_company_auth_success_acme():
    """Verify combined company authentication succeeds with valid password and Google ID token."""
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
        response = client.post(
            "/auth/company",
            json={
                "tenant_id": "acme",
                "password": "AcmeSecret2026!",
                "google_id_token": "valid.mock.google.id.token",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["tenant_id"] == "acme"
    assert data["google_sub"] == "google-user-1234567890"
    assert data["email"] == "developer@example.com"
    assert "access_token" in data
    assert len(data["access_token"]) > 20
    assert data["expires_in"] > 0
    assert "Acme Corp" in data["message"]


def test_company_auth_success_globex():
    """Verify combined company authentication succeeds with valid password for tenant 'globex'."""
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
        response = client.post(
            "/auth/company",
            json={
                "tenant_id": "globex",
                "password": "GlobexSecret2026!",
                "google_id_token": "valid.mock.google.id.token",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["tenant_id"] == "globex"
    assert data["google_sub"] == "google-user-1234567890"
    assert data["email"] == "developer@example.com"
    assert "access_token" in data
    assert "Globex Corporation" in data["message"]


def test_company_auth_invalid_password_returns_401():
    """Verify company authentication fails with 401 when given an incorrect password."""
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
        response = client.post(
            "/auth/company",
            json={
                "tenant_id": "acme",
                "password": "WrongPassword123!",
                "google_id_token": "valid.mock.google.id.token",
            },
        )
    assert response.status_code == 401
    data = response.json()
    assert "Invalid tenant ID or password" in data["detail"]


def test_company_auth_unknown_tenant_returns_401():
    """Verify company authentication fails with 401 for an unknown tenant ID."""
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
        response = client.post(
            "/auth/company",
            json={
                "tenant_id": "unknown_corp",
                "password": "SomePassword!",
                "google_id_token": "valid.mock.google.id.token",
            },
        )
    assert response.status_code == 401
    data = response.json()
    assert "Invalid tenant ID or password" in data["detail"]


def test_company_auth_missing_google_token_returns_422():
    """Verify company authentication returns 422 if google_id_token is missing."""
    response = client.post(
        "/auth/company",
        json={"tenant_id": "acme", "password": "AcmeSecret2026!"},
    )
    assert response.status_code in (400, 422)


def test_company_auth_invalid_google_token_returns_401():
    """Verify company authentication fails with 401 if Google ID token is invalid or expired."""
    with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token invalid")):
        response = client.post(
            "/auth/company",
            json={
                "tenant_id": "acme",
                "password": "AcmeSecret2026!",
                "google_id_token": "bad.google.id.token",
            },
        )
    assert response.status_code == 401
    data = response.json()
    assert "Google ID token" in data["detail"]


def test_switch_company_success():
    """Verify switching company with client-held Google ID token issues a new scoped token without re-login."""
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
        response = client.post(
            "/auth/switch-company",
            json={
                "new_tenant_id": "globex",
                "password": "GlobexSecret2026!",
                "google_id_token": "valid.client.google.token",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["tenant_id"] == "globex"
    assert data["google_sub"] == "google-user-1234567890"
    assert data["email"] == "developer@example.com"
    assert "access_token" in data
    assert "Globex Corporation" in data["message"]


def test_switch_company_invalid_password_returns_401():
    """Verify switching company fails with 401 when target company password is wrong."""
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
        response = client.post(
            "/auth/switch-company",
            json={
                "new_tenant_id": "globex",
                "password": "WrongPassword2026!",
                "google_id_token": "valid.client.google.token",
            },
        )
    assert response.status_code == 401
    data = response.json()
    assert "Invalid company password" in data["detail"]


def test_switch_company_unknown_tenant_returns_422():
    """Verify switching company to an unregistered tenant returns 422."""
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
        response = client.post(
            "/auth/switch-company",
            json={
                "new_tenant_id": "nonexistent_tenant",
                "password": "SomePassword123!",
                "google_id_token": "valid.client.google.token",
            },
        )
    assert response.status_code == 422
    data = response.json()
    assert "Unknown tenant" in data["detail"]


def test_switch_company_invalid_google_token_returns_401():
    """Verify switching company fails with 401 when Google ID token has expired or is invalid."""
    with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token expired")):
        response = client.post(
            "/auth/switch-company",
            json={
                "new_tenant_id": "globex",
                "password": "GlobexSecret2026!",
                "google_id_token": "expired.client.google.token",
            },
        )
    assert response.status_code == 401
    data = response.json()
    assert "Google ID token" in data["detail"]


# ---------------------------------------------------------------------------
# Google Sign-In Authentication (/auth/google)
# ---------------------------------------------------------------------------

def test_google_auth_config():
    """Verify GET /auth/google/config returns Google OAuth Client configuration."""
    response = client.get("/auth/google/config")
    assert response.status_code == 200
    data = response.json()
    assert "client_id" in data
    assert "enabled" in data


def test_google_auth_success():
    """Verify POST /auth/google verifies Google ID token and returns stable user ID and email."""
    mock_id_info = {
        "sub": "google-user-1234567890",
        "email": "developer@example.com",
        "email_verified": True,
        "name": "Alex Smith",
        "picture": "https://lh3.googleusercontent.com/a/test-avatar",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_id_info):
        response = client.post(
            "/auth/google",
            json={"id_token": "valid.mock.google.id.token.string"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["google_user_id"] == "google-user-1234567890"
        assert data["email"] == "developer@example.com"
        assert data["email_verified"] is True
        assert data["name"] == "Alex Smith"
        assert data["picture"] == "https://lh3.googleusercontent.com/a/test-avatar"
        assert "developer@example.com" in data["message"]


def test_google_auth_invalid_token_returns_401():
    """Verify POST /auth/google rejects invalid or expired Google ID tokens with HTTP 401."""
    with patch(
        "google.oauth2.id_token.verify_oauth2_token",
        side_effect=ValueError("Token used too early or expired"),
    ):
        response = client.post(
            "/auth/google",
            json={"id_token": "expired.invalid.token.payload"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "Invalid or expired Google ID token" in data["detail"]


def test_google_auth_missing_sub_returns_401():
    """Verify POST /auth/google rejects tokens missing the required 'sub' claim with HTTP 401."""
    mock_id_info = {
        "email": "developer@example.com",
        "email_verified": True,
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_id_info):
        response = client.post(
            "/auth/google",
            json={"id_token": "token.without.sub.claim"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "missing required 'sub' claim" in data["detail"].lower()


def test_google_auth_missing_email_returns_401():
    """Verify POST /auth/google rejects tokens missing the required 'email' claim with HTTP 401."""
    mock_id_info = {
        "sub": "google-user-1234567890",
        "email_verified": True,
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_id_info):
        response = client.post(
            "/auth/google",
            json={"id_token": "token.without.email.claim"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "missing required 'email' claim" in data["detail"].lower()


def test_google_auth_missing_id_token_returns_422():
    """Verify POST /auth/google returns 422 when id_token field is missing or empty."""
    response = client.post("/auth/google", json={})
    assert response.status_code in (400, 422)

    response_empty = client.post("/auth/google", json={"id_token": ""})
    assert response_empty.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Authorization & Cross-Tenant Boundary Enforcement (/query)
# ---------------------------------------------------------------------------

def test_query_missing_auth_header_returns_401():
    """Verify that POST /query rejects requests without an Authorization header with HTTP 401."""
    payload = {
        "tenant_id": "acme",
        "question": "What is the probation period?",
    }
    response = client.post("/query", json=payload)
    assert response.status_code == 401
    assert "missing authorization header" in response.json()["detail"].lower()


def test_query_malformed_auth_header_returns_401():
    """Verify that POST /query rejects malformed Authorization headers with HTTP 401."""
    payload = {
        "tenant_id": "acme",
        "question": "What is the probation period?",
    }
    response = client.post("/query", json=payload, headers={"Authorization": "Basic 12345"})
    assert response.status_code == 401
    assert "malformed authorization header" in response.json()["detail"].lower()


def test_query_invalid_token_returns_401():
    """Verify that POST /query rejects forged or invalid tokens with HTTP 401."""
    payload = {
        "tenant_id": "acme",
        "question": "What is the probation period?",
    }
    response = client.post(
        "/query",
        json=payload,
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert response.status_code == 401
    assert "invalid authorization token" in response.json()["detail"].lower()


def test_query_cross_tenant_token_returns_403_forbidden():
    """Verify that using a token scoped to 'acme' to query 'globex' is blocked with HTTP 403 Forbidden."""
    acme_headers = get_auth_headers("acme")
    payload = {
        "tenant_id": "globex",
        "question": "What is the security clearance protocol?",
    }
    response = client.post("/query", json=payload, headers=acme_headers)
    assert response.status_code == 403
    data = response.json()
    assert "access forbidden" in data["detail"].lower()
    assert "does not match the requested tenant" in data["detail"].lower()


# ---------------------------------------------------------------------------
# Query Pipeline Tests (With Valid Auth)
# ---------------------------------------------------------------------------

def test_query_valid_tenant_acme():
    """Verify that POST /query succeeds for valid tenant 'acme'."""
    payload = {
        "tenant_id": "acme",
        "question": "What is the probation period duration?",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == "acme"
    assert data["tenant_name"] == "Acme Corp"
    assert data["question"] == "What is the probation period duration?"
    assert "Acme Corp" in data["message"]


def test_query_valid_tenant_globex():
    """Verify that POST /query succeeds for valid tenant 'globex'."""
    payload = {
        "tenant_id": "globex",
        "question": "What is the security clearance protocol?",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("globex"))
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == "globex"
    assert data["tenant_name"] == "Globex Corporation"
    assert data["question"] == "What is the security clearance protocol?"


def test_query_unknown_tenant_returns_400():
    """Verify that POST /query rejects unknown tenants with HTTP 400 or 422."""
    payload = {
        "tenant_id": "initech",
        "question": "What is the dress code?",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("initech"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "detail" in data
    assert "Unknown tenant 'initech'" in data["detail"]
    assert "Available configured tenants:" in data["detail"]


def test_query_empty_question_returns_400():
    """Verify that POST /query rejects empty or whitespace-only questions with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
        "question": "   ",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "cannot be empty" in data["detail"].lower()


def test_query_empty_string_question_returns_400():
    """Verify that POST /query rejects empty string questions with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
        "question": "",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "cannot be empty" in data["detail"].lower()


def test_query_oversized_question_returns_400():
    """Verify that POST /query rejects questions exceeding maximum allowed length with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
        "question": "A" * 501,
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "exceeds maximum allowed length" in data["detail"].lower()


def test_query_missing_question_field_returns_400():
    """Verify that POST /query rejects requests missing the required 'question' field with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "malformed request" in data["detail"].lower()
    assert "missing required field 'question'" in data["detail"].lower()


def test_query_missing_tenant_id_field_returns_400():
    """Verify that POST /query rejects requests missing the required 'tenant_id' field with HTTP 400 or 422."""
    payload = {
        "question": "What is the probation period?",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "malformed request" in data["detail"].lower()
    assert "missing required field 'tenant_id'" in data["detail"].lower()


def test_query_empty_tenant_id_returns_400():
    """Verify that POST /query rejects empty or whitespace-only tenant_id with HTTP 400 or 422."""
    payload = {
        "tenant_id": "   ",
        "question": "What is the probation period?",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "cannot be empty" in data["detail"].lower()


def test_query_malformed_json_body_returns_400():
    """Verify that POST /query rejects invalid JSON syntax with HTTP 400."""
    headers = get_auth_headers("acme")
    headers["Content-Type"] = "application/json"
    response = client.post(
        "/query",
        content=b"{invalid_json_payload",
        headers=headers,
    )
    assert response.status_code in (400, 422)
    data = response.json()
    assert "malformed request" in data["detail"].lower()


def test_query_invalid_top_k_type_returns_400():
    """Verify that POST /query rejects invalid top_k types with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
        "question": "What is the probation period?",
        "top_k": "not_an_int",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "top_k" in data["detail"].lower()


def test_query_invalid_top_k_out_of_bounds_returns_400():
    """Verify that POST /query rejects out-of-bounds top_k with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
        "question": "What is the probation period?",
        "top_k": 25,
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code in (400, 422)
    data = response.json()
    assert "top_k" in data["detail"].lower()


def test_query_case_insensitivity():
    """Verify that tenant_id is normalized (case-insensitive)."""
    payload = {
        "tenant_id": "ACME",
        "question": "What are working hours?",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == "acme"


def test_serve_acme_pdf_statically():
    """Verify that Acme handbook PDF is served statically from /documents/."""
    response = client.get("/documents/Acme Corp Employee Handbook.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 10000


def test_serve_globex_pdf_statically():
    """Verify that Globex handbook PDF is served statically from /documents/."""
    response = client.get("/documents/Globex Corporation Employee Handbook.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 10000


def test_serve_nonexistent_pdf_returns_404():
    """Verify that requesting a missing PDF returns HTTP 404."""
    response = client.get("/documents/nonexistent_handbook.pdf")
    assert response.status_code == 404


def test_small_talk_skips_retrieval_and_llm():
    """Verify that small-talk queries return direct friendly replies without touching vector store or LLM."""
    with patch("api.main.retrieve_tenant_chunks") as mock_retrieve, \
         patch("api.main.get_llm_adapter") as mock_llm:

        for phrase in ["hi", "hello", "hey", "how are you?", "thanks", "who are you", "bye!"]:
            response = client.post(
                "/query",
                json={"tenant_id": "acme", "question": phrase},
                headers=get_auth_headers("acme"),
            )
            assert response.status_code == 200
            data = response.json()
            assert data["tenant_id"] == "acme"
            assert data["chunks_retrieved"] == 0
            assert data["sources"] == []
            assert len(data["answer"]) > 0

        # Verify that retrieval and LLM calls were completely bypassed
        mock_retrieve.assert_not_called()
        mock_llm.assert_not_called()


def test_query_control_characters_in_question_rejected_with_422():
    """Verify that POST /query rejects questions with unprintable control characters with HTTP 422."""
    for char, name in [("\x00", "null byte"), ("\x1b", "escape"), ("\x08", "backspace")]:
        payload = {
            "tenant_id": "acme",
            "question": f"What is the policy?{char}",
        }
        response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
        assert response.status_code == 422
        data = response.json()
        assert "control character" in data["detail"].lower()
        assert "question" in data["detail"].lower()


def test_query_control_characters_in_tenant_id_rejected_with_422():
    """Verify that POST /query rejects tenant_id with unprintable control characters with HTTP 422."""
    payload = {
        "tenant_id": "acme\x00corp",
        "question": "What is the policy?",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code == 422
    data = response.json()
    assert "control character" in data["detail"].lower()
    assert "tenant_id" in data["detail"].lower()


def test_query_binary_content_type_rejected_with_422():
    """Verify that binary Content-Type headers are rejected with HTTP 422 and a clear explanation."""
    headers = get_auth_headers("acme")
    headers["Content-Type"] = "application/octet-stream"
    response = client.post(
        "/query",
        content=b'{"tenant_id": "acme", "question": "test"}',
        headers=headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert "binary payloads are not supported" in data["detail"].lower()


def test_query_non_utf8_payload_rejected_with_422():
    """Verify that non-UTF-8 binary byte sequences in the request body are rejected with HTTP 422."""
    headers = get_auth_headers("acme")
    headers["Content-Type"] = "application/json"
    response = client.post(
        "/query",
        content=b"\xff\xfe\x00\x01\x80\x81",
        headers=headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert "not valid utf-8" in data["detail"].lower()


def test_query_unknown_tenant_returns_strict_422_with_reason():
    """Verify that an unknown tenant returns HTTP 422 listing all available tenants."""
    payload = {
        "tenant_id": "nonexistent_corp",
        "question": "What is the policy?",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("nonexistent_corp"))
    assert response.status_code == 422
    data = response.json()
    assert "Unknown tenant 'nonexistent_corp'" in data["detail"]
    assert "Available configured tenants:" in data["detail"]


def test_query_whitespace_question_returns_strict_422():
    """Verify that whitespace-only question returns HTTP 422 with a specific reason."""
    payload = {
        "tenant_id": "acme",
        "question": "    \t\n   ",
    }
    response = client.post("/query", json=payload, headers=get_auth_headers("acme"))
    assert response.status_code == 422
    data = response.json()
    assert "cannot be empty or contain only whitespace" in data["detail"].lower()
