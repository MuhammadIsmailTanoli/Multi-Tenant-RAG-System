"""Unit and integration tests for FastAPI query endpoints.

Verifies:
1. POST /query validates tenant_id against tenants.yaml.
2. Returns HTTP 400 Bad Request for unknown or unauthorized tenants.
3. Returns HTTP 400 Bad Request for empty questions.
4. Returns HTTP 200 OK for valid registered tenants (e.g., 'acme', 'globex').
5. Health and tenant listing endpoints report correct metadata.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


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
    """Verify that POST /query rejects unknown tenants with HTTP 400."""
    payload = {
        "tenant_id": "initech",
        "question": "What is the dress code?",
    }
    response = client.post("/query", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Unknown tenant 'initech'" in data["detail"]
    assert "Available configured tenants:" in data["detail"]


def test_query_empty_question_returns_400():
    """Verify that POST /query rejects empty or whitespace-only questions with HTTP 400."""
    payload = {
        "tenant_id": "acme",
        "question": "   ",
    }
    response = client.post("/query", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert "cannot be empty" in data["detail"].lower()


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
