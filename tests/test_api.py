"""Unit and integration tests for FastAPI query endpoints.

Verifies:
1. POST /query validates tenant_id against tenants.yaml.
2. Returns HTTP 400 Bad Request for unknown or unauthorized tenants.
3. Returns HTTP 400 Bad Request for empty questions.
4. Returns HTTP 200 OK for valid registered tenants (e.g., 'acme', 'globex').
5. Health and tenant listing endpoints report correct metadata.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_llm_adapter_for_tests():
    """Mock LLM adapter to ensure tests execute offline deterministically and without quota limits."""
    mock_adapter = MagicMock()
    mock_adapter.provider_name = "mock-provider"
    mock_adapter.model_name = "mock-model"
    mock_adapter.generate_answer.return_value = "Mock answer grounded in handbook policies."
    with patch("api.main.get_llm_adapter", return_value=mock_adapter):
        yield mock_adapter


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


def test_query_valid_tenant_acme():
    """Verify that POST /query succeeds for valid tenant 'acme'."""
    payload = {
        "tenant_id": "acme",
        "question": "What is the probation period duration?",
    }
    response = client.post("/query", json=payload)
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
    response = client.post("/query", json=payload)
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
    response = client.post("/query", json=payload)
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
    response = client.post("/query", json=payload)
    assert response.status_code in (400, 422)
    data = response.json()
    assert "cannot be empty" in data["detail"].lower()


def test_query_empty_string_question_returns_400():
    """Verify that POST /query rejects empty string questions with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
        "question": "",
    }
    response = client.post("/query", json=payload)
    assert response.status_code in (400, 422)
    data = response.json()
    assert "cannot be empty" in data["detail"].lower()


def test_query_oversized_question_returns_400():
    """Verify that POST /query rejects questions exceeding maximum allowed length with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
        "question": "A" * 1001,
    }
    response = client.post("/query", json=payload)
    assert response.status_code in (400, 422)
    data = response.json()
    assert "exceeds maximum allowed length" in data["detail"].lower()


def test_query_missing_question_field_returns_400():
    """Verify that POST /query rejects requests missing the required 'question' field with HTTP 400 or 422."""
    payload = {
        "tenant_id": "acme",
    }
    response = client.post("/query", json=payload)
    assert response.status_code in (400, 422)
    data = response.json()
    assert "malformed request" in data["detail"].lower()
    assert "missing required field 'question'" in data["detail"].lower()


def test_query_missing_tenant_id_field_returns_400():
    """Verify that POST /query rejects requests missing the required 'tenant_id' field with HTTP 400 or 422."""
    payload = {
        "question": "What is the probation period?",
    }
    response = client.post("/query", json=payload)
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
    response = client.post("/query", json=payload)
    assert response.status_code in (400, 422)
    data = response.json()
    assert "cannot be empty" in data["detail"].lower()


def test_query_malformed_json_body_returns_400():
    """Verify that POST /query rejects invalid JSON syntax with HTTP 400."""
    response = client.post(
        "/query",
        content=b"{invalid_json_payload",
        headers={"Content-Type": "application/json"},
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
    response = client.post("/query", json=payload)
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
    response = client.post("/query", json=payload)
    assert response.status_code in (400, 422)
    data = response.json()
    assert "top_k" in data["detail"].lower()


def test_query_case_insensitivity():
    """Verify that tenant_id is normalized (case-insensitive)."""
    payload = {
        "tenant_id": "ACME",
        "question": "What are working hours?",
    }
    response = client.post("/query", json=payload)
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


def test_root_endpoint_metadata():
    """Verify root endpoint advertises available endpoints including /documents."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data["endpoints"]
    assert "/documents/{filename}" in data["endpoints"]["documents"]


def test_small_talk_skips_retrieval_and_llm():
    """Verify that small-talk queries return direct friendly replies without touching vector store or LLM."""
    with patch("api.main.retrieve_tenant_chunks") as mock_retrieve, \
         patch("api.main.get_llm_adapter") as mock_llm:

        for phrase in ["hi", "hello", "hey", "how are you?", "thanks", "who are you", "bye!"]:
            response = client.post("/query", json={"tenant_id": "acme", "question": phrase})
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
        response = client.post("/query", json=payload)
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
    response = client.post("/query", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "control character" in data["detail"].lower()
    assert "tenant_id" in data["detail"].lower()


def test_query_binary_content_type_rejected_with_422():
    """Verify that binary Content-Type headers are rejected with HTTP 422 and a clear explanation."""
    response = client.post(
        "/query",
        content=b'{"tenant_id": "acme", "question": "test"}',
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 422
    data = response.json()
    assert "binary payloads are not supported" in data["detail"].lower()


def test_query_non_utf8_payload_rejected_with_422():
    """Verify that non-UTF-8 binary byte sequences in the request body are rejected with HTTP 422."""
    response = client.post(
        "/query",
        content=b"\xff\xfe\x00\x01\x80\x81",
        headers={"Content-Type": "application/json"},
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
    response = client.post("/query", json=payload)
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
    response = client.post("/query", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "cannot be empty or contain only whitespace" in data["detail"].lower()


