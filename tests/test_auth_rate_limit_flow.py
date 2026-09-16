"""Comprehensive tests for full authentication + rate-limiting flow.

Validates the complete end-to-end security and rate limiting lifecycle:
1. A company session token cannot be issued without a valid Google identity token.
2. Switching companies with an existing Google session only requires the new company's password.
3. Expired, tampered, or mismatched-tenant tokens are rejected with appropriate HTTP statuses (401/403).
4. Rate limits persist correctly across a company switch for the same Google user identity.
5. A user is blocked with HTTP 429 after exceeding daily and weekly limits independently.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.auth import create_tenant_token
from api.rate_limiter import limiter
from ingestion.config import get_settings

client = TestClient(app)

MOCK_GOOGLE_SUB = "google-user-session-9876543210"
MOCK_GOOGLE_EMAIL = "alex.developer@example.com"
MOCK_GOOGLE_ID_INFO = {
    "sub": MOCK_GOOGLE_SUB,
    "email": MOCK_GOOGLE_EMAIL,
    "email_verified": True,
    "name": "Alex Developer",
    "picture": "https://lh3.googleusercontent.com/a/test-avatar-profile",
}


@pytest.fixture(autouse=True)
def reset_rate_limiter_fixture():
    """Reset rate limiter counters before and after each test for clean isolation."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def mock_llm_adapter_for_tests():
    """Mock LLM adapter to ensure tests execute offline deterministically."""
    mock_adapter = MagicMock()
    mock_adapter.provider_name = "mock-provider"
    mock_adapter.model_name = "mock-model"
    mock_adapter.generate_answer.return_value = "Verified handbook policy answer."
    with patch("api.main.get_llm_adapter", return_value=mock_adapter):
        yield mock_adapter


@pytest.fixture(autouse=True)
def mock_retriever_for_tests():
    """Mock retriever to ensure tests execute instantaneously without loading embeddings."""
    from api.retriever import RetrievedChunk

    def _mock_retrieve(tenant_id: str, question: str, top_k: int = 4, **kwargs):
        return [
            RetrievedChunk(
                chunk_id=f"{tenant_id}_chunk_0",
                text=f"Official policy context for {tenant_id} on {question}.",
                tenant_id=tenant_id,
                source_file=f"{tenant_id.capitalize()} Employee Handbook.pdf",
                page_start=1,
                page_end=2,
                chunk_index=0,
                token_count=60,
                distance=0.1,
                similarity=0.92,
            )
        ]

    with patch("api.main.retrieve_tenant_chunks", side_effect=_mock_retrieve) as mock_retriever:
        yield mock_retriever


# ===========================================================================
# 1. Company Token Requires Valid Google Identity Token
# ===========================================================================

class TestCompanyTokenRequiresValidGoogleIdentity:
    """Confirms a company token cannot be issued without a valid Google identity token."""

    def test_company_token_rejected_when_google_token_is_missing(self):
        """POST /auth/company must fail when google_id_token is omitted from the request body."""
        response = client.post(
            "/auth/company",
            json={
                "tenant_id": "acme",
                "password": "AcmeSecret2026!",
            },
        )
        assert response.status_code in (400, 422)

    def test_company_token_rejected_when_google_token_is_empty(self):
        """POST /auth/company must fail when google_id_token is an empty string."""
        response = client.post(
            "/auth/company",
            json={
                "tenant_id": "acme",
                "password": "AcmeSecret2026!",
                "google_id_token": "",
            },
        )
        assert response.status_code in (400, 422)

    def test_company_token_rejected_when_google_token_is_invalid_or_forged(self):
        """POST /auth/company must fail with 401 when google_id_token fails cryptographic verification."""
        with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token signature forged")):
            response = client.post(
                "/auth/company",
                json={
                    "tenant_id": "acme",
                    "password": "AcmeSecret2026!",
                    "google_id_token": "forged.header.payload.signature",
                },
            )
        assert response.status_code == 401
        data = response.json()
        assert "Google ID token" in data["detail"]

    def test_company_token_rejected_when_google_token_missing_sub_claim(self):
        """POST /auth/company must fail with 401 when Google ID token has no 'sub' user identifier claim."""
        incomplete_id_info = {
            "email": "no-sub@example.com",
            "name": "No Sub",
        }
        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=incomplete_id_info):
            response = client.post(
                "/auth/company",
                json={
                    "tenant_id": "acme",
                    "password": "AcmeSecret2026!",
                    "google_id_token": "token.without.sub",
                },
            )
        assert response.status_code == 401
        assert "sub" in response.json()["detail"].lower()

    def test_company_token_rejected_when_password_is_wrong_despite_valid_google_token(self):
        """POST /auth/company must fail with 401 when Google token is valid but company password is wrong."""
        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
            response = client.post(
                "/auth/company",
                json={
                    "tenant_id": "acme",
                    "password": "IncorrectPassword123!",
                    "google_id_token": "valid.mock.google.id.token",
                },
            )
        assert response.status_code == 401
        assert "Invalid tenant ID or password" in response.json()["detail"]

    def test_company_token_succeeds_with_valid_google_token_and_valid_password(self):
        """POST /auth/company must succeed and return a combined JWT containing tenant_id and google_sub."""
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
        assert data["google_sub"] == MOCK_GOOGLE_SUB
        assert data["email"] == MOCK_GOOGLE_EMAIL
        assert "access_token" in data
        assert len(data["access_token"]) > 20
        assert data["expires_in"] > 0


# ===========================================================================
# 2. Switching Companies with Existing Google Session Only Requires New Password
# ===========================================================================

class TestSwitchCompanySessionFlow:
    """Confirms switching companies with an existing Google session only requires the new password."""

    def test_switch_company_with_existing_google_session_only_requires_new_password(self):
        """User holding an existing Google ID token switches to Globex by providing only the new password."""
        # Initial login to Acme with Google session
        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
            acme_resp = client.post(
                "/auth/company",
                json={
                    "tenant_id": "acme",
                    "password": "AcmeSecret2026!",
                    "google_id_token": "valid.client.google.token",
                },
            )
            assert acme_resp.status_code == 200
            assert acme_resp.json()["tenant_id"] == "acme"

            # Switch company to Globex using client-held Google ID token and new password only
            switch_resp = client.post(
                "/auth/switch-company",
                json={
                    "new_tenant_id": "globex",
                    "password": "GlobexSecret2026!",
                    "google_id_token": "valid.client.google.token",
                },
            )

        assert switch_resp.status_code == 200
        switch_data = switch_resp.json()
        assert switch_data["tenant_id"] == "globex"
        assert switch_data["google_sub"] == MOCK_GOOGLE_SUB
        assert switch_data["email"] == MOCK_GOOGLE_EMAIL
        assert "Globex Corporation" in switch_data["message"]

        # The newly issued token immediately allows querying Globex
        globex_headers = {"Authorization": f"Bearer {switch_data['access_token']}"}
        query_resp = client.post(
            "/query",
            json={"tenant_id": "globex", "question": "What is the probation policy?"},
            headers=globex_headers,
        )
        assert query_resp.status_code == 200
        assert query_resp.json()["tenant_id"] == "globex"

    def test_switch_company_fails_with_invalid_new_company_password(self):
        """POST /auth/switch-company must fail with 401 when the password for the new company is incorrect."""
        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
            response = client.post(
                "/auth/switch-company",
                json={
                    "new_tenant_id": "globex",
                    "password": "WrongGlobexPassword!",
                    "google_id_token": "valid.client.google.token",
                },
            )
        assert response.status_code == 401
        assert "Invalid company password" in response.json()["detail"]

    def test_switch_company_fails_with_invalid_google_token(self):
        """POST /auth/switch-company must fail with 401 if client-held Google token is invalid or expired."""
        with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token expired")):
            response = client.post(
                "/auth/switch-company",
                json={
                    "new_tenant_id": "globex",
                    "password": "GlobexSecret2026!",
                    "google_id_token": "expired.google.token",
                },
            )
        assert response.status_code == 401
        assert "Google ID token" in response.json()["detail"]

    def test_switch_company_fails_for_unknown_tenant(self):
        """POST /auth/switch-company must reject nonexistent or unregistered tenants."""
        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=MOCK_GOOGLE_ID_INFO):
            response = client.post(
                "/auth/switch-company",
                json={
                    "new_tenant_id": "nonexistent_tenant",
                    "password": "SomePassword123!",
                    "google_id_token": "valid.client.google.token",
                },
            )
        assert response.status_code in (400, 422)


# ===========================================================================
# 3. Expired or Mismatched-Tenant Token is Rejected
# ===========================================================================

class TestTokenValidationAndRejection:
    """Confirms expired, mismatched-tenant, or tampered tokens are rejected."""

    def test_expired_token_is_rejected_with_401(self):
        """POST /query must return HTTP 401 Unauthorized when presented with an expired JWT token."""
        # Create an expired token (expired 60 seconds ago)
        expired_token = create_tenant_token(
            tenant_id="acme",
            google_sub=MOCK_GOOGLE_SUB,
            expires_delta=timedelta(seconds=-60),
        )
        headers = {"Authorization": f"Bearer {expired_token}"}

        response = client.post(
            "/query",
            json={"tenant_id": "acme", "question": "What is the probation period?"},
            headers=headers,
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_mismatched_tenant_token_is_rejected_with_403(self):
        """POST /query must return HTTP 403 Forbidden when a token scoped to Acme queries Globex."""
        acme_token = create_tenant_token(tenant_id="acme", google_sub=MOCK_GOOGLE_SUB)
        headers = {"Authorization": f"Bearer {acme_token}"}

        # Attempt to access globex using Acme-scoped token
        response = client.post(
            "/query",
            json={"tenant_id": "globex", "question": "What is the probation period?"},
            headers=headers,
        )
        assert response.status_code == 403
        data = response.json()
        assert "forbidden" in data["detail"].lower()
        assert "scoped to tenant 'acme'" in data["detail"]
        assert "globex" in data["detail"]

    def test_tampered_token_signature_is_rejected_with_401(self):
        """POST /query must return HTTP 401 Unauthorized when the JWT signature is invalid or modified."""
        valid_token = create_tenant_token(tenant_id="acme", google_sub=MOCK_GOOGLE_SUB)
        tampered_token = valid_token[:-6] + "xyz123"
        headers = {"Authorization": f"Bearer {tampered_token}"}

        response = client.post(
            "/query",
            json={"tenant_id": "acme", "question": "What is the probation period?"},
            headers=headers,
        )
        assert response.status_code == 401
        assert "Invalid authorization token" in response.json()["detail"]

    def test_missing_authorization_header_rejected_with_401(self):
        """POST /query must return HTTP 401 Unauthorized when no Authorization header is provided."""
        response = client.post(
            "/query",
            json={"tenant_id": "acme", "question": "What is the probation period?"},
        )
        assert response.status_code == 401
        assert "Missing Authorization header" in response.json()["detail"]


# ===========================================================================
# 4. Rate Limits Persist Correctly Across Company Switch for Same Google User
# ===========================================================================

class TestRateLimitPersistenceAcrossCompanySwitch:
    """Confirms rate limits persist across company switches for the same Google identity."""

    def test_rate_limits_persist_across_company_switch_for_same_google_user(self):
        """Query counts accumulated under Acme carry forward seamlessly when switching to Globex."""
        shared_user_sub = "google-user-switch-persistence-test"
        acme_token = create_tenant_token("acme", google_sub=shared_user_sub)
        acme_headers = {"Authorization": f"Bearer {acme_token}"}

        # User performs 15 queries under Acme
        for i in range(15):
            res = client.post(
                "/query",
                json={"tenant_id": "acme", "question": f"Question {i} under Acme"},
                headers=acme_headers,
            )
            assert res.status_code == 200

        # Check limits endpoint under Acme: 15 used, 35 remaining
        limits_acme = client.get("/limits", headers=acme_headers).json()
        daily_stat_acme = next(item for item in limits_acme["limits"] if item["period"] == "day")
        assert daily_stat_acme["count"] == 15
        assert daily_stat_acme["remaining"] == 35

        # Switch company to Globex (same Google user)
        globex_token = create_tenant_token("globex", google_sub=shared_user_sub)
        globex_headers = {"Authorization": f"Bearer {globex_token}"}

        # Check limits endpoint under Globex: still shows 15 used, 35 remaining!
        limits_globex = client.get("/limits", headers=globex_headers).json()
        daily_stat_globex = next(item for item in limits_globex["limits"] if item["period"] == "day")
        assert daily_stat_globex["count"] == 15
        assert daily_stat_globex["remaining"] == 35

        # User performs 10 queries under Globex
        for i in range(10):
            res = client.post(
                "/query",
                json={"tenant_id": "globex", "question": f"Question {i} under Globex"},
                headers=globex_headers,
            )
            assert res.status_code == 200

        # Total count across both companies is now 25
        limits_after = client.get("/limits", headers=globex_headers).json()
        daily_stat_after = next(item for item in limits_after["limits"] if item["period"] == "day")
        assert daily_stat_after["count"] == 25
        assert daily_stat_after["remaining"] == 25

    def test_rate_limit_quota_exhaustion_blocks_both_companies_after_switch(self):
        """Exhausting quota under one company blocks querying under the switched company as well."""
        shared_user_sub = "google-user-exhaustion-across-companies"
        acme_token = create_tenant_token("acme", google_sub=shared_user_sub)
        globex_token = create_tenant_token("globex", google_sub=shared_user_sub)

        # Set user count directly in storage to 50 for the daily limit
        daily_key = f"LIMITER/google_user:{shared_user_sub}//query/50/1/day"
        limiter._storage.incr(daily_key, expiry=86400, amount=50)

        # Querying under Globex is immediately blocked with HTTP 429
        res_globex = client.post(
            "/query",
            json={"tenant_id": "globex", "question": "Can I query Globex now?"},
            headers={"Authorization": f"Bearer {globex_token}"},
        )
        assert res_globex.status_code == 429
        assert "Rate limit exceeded" in res_globex.json()["detail"]
        assert "Real user query limit reached across all companies" in res_globex.json()["detail"]

        # Querying under Acme is also blocked with HTTP 429
        res_acme = client.post(
            "/query",
            json={"tenant_id": "acme", "question": "Can I query Acme now?"},
            headers={"Authorization": f"Bearer {acme_token}"},
        )
        assert res_acme.status_code == 429
        assert "Rate limit exceeded" in res_acme.json()["detail"]


# ===========================================================================
# 5. User Blocked with 429 After Exceeding Daily and Weekly Limits Independently
# ===========================================================================

class TestIndependentDailyAndWeeklyRateLimits:
    """Confirms user is blocked with HTTP 429 after exceeding daily and weekly limits independently."""

    def test_daily_rate_limit_blocks_with_429_independently(self):
        """User hitting 50 queries in a day is blocked by the daily limit independently (weekly count < 200)."""
        daily_user = "google-user-daily-independent-test"
        headers = {"Authorization": f"Bearer {create_tenant_token('acme', google_sub=daily_user)}"}

        # Simulate 50 queries consumed today (weekly counter is at 50, well below 200)
        daily_key = f"LIMITER/google_user:{daily_user}//query/50/1/day"
        weekly_key = f"LIMITER/google_user:{daily_user}//query/200/7/day"
        limiter._storage.incr(daily_key, expiry=86400, amount=50)
        limiter._storage.incr(weekly_key, expiry=604800, amount=50)

        # 51st query today must be blocked by the DAILY limit
        response = client.post(
            "/query",
            json={"tenant_id": "acme", "question": "Daily limit trigger question"},
            headers=headers,
        )
        assert response.status_code == 429
        data = response.json()
        assert "Rate limit exceeded" in data["detail"]
        assert "50 per 1 day" in data["limit"]
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0
        assert data["reset_epoch"] > 0

    def test_weekly_rate_limit_blocks_with_429_independently(self):
        """User hitting 200 queries in a week is blocked by weekly limit even when daily count is low."""
        weekly_user = "google-user-weekly-independent-test"
        headers = {"Authorization": f"Bearer {create_tenant_token('globex', google_sub=weekly_user)}"}

        # Simulate user having consumed 200 queries over the week, but today's daily count is only 5
        daily_key = f"LIMITER/google_user:{weekly_user}//query/50/1/day"
        weekly_key = f"LIMITER/google_user:{weekly_user}//query/200/7/day"
        limiter._storage.incr(daily_key, expiry=86400, amount=5)
        limiter._storage.incr(weekly_key, expiry=604800, amount=200)

        # Next query must be blocked by the WEEKLY limit, NOT daily (daily is 5 < 50)
        response = client.post(
            "/query",
            json={"tenant_id": "globex", "question": "Weekly limit trigger question"},
            headers=headers,
        )
        assert response.status_code == 429
        data = response.json()
        assert "Rate limit exceeded" in data["detail"]
        # slowapi parses '200/7 days' into limit string '200 per 7 day' or '200 per 7 days'
        assert "200 per 7 day" in data["limit"]
        assert "Retry-After" in response.headers
        assert int(response.headers["Retry-After"]) > 0
        assert data["reset_epoch"] > 0

    def test_daily_and_weekly_limits_report_correct_live_metrics_in_limits_endpoint(self):
        """GET /limits correctly reports both daily and weekly independent metrics for the user."""
        metrics_user = "google-user-metrics-dual-check"
        headers = {"Authorization": f"Bearer {create_tenant_token('acme', google_sub=metrics_user)}"}

        daily_key = f"LIMITER/google_user:{metrics_user}//query/50/1/day"
        weekly_key = f"LIMITER/google_user:{metrics_user}//query/200/7/day"
        limiter._storage.incr(daily_key, expiry=86400, amount=25)
        limiter._storage.incr(weekly_key, expiry=604800, amount=75)

        res = client.get("/limits", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["authenticated"] is True
        assert data["google_sub"] == metrics_user

        daily_item = next(item for item in data["limits"] if item["period"] == "day")
        weekly_item = next(item for item in data["limits"] if item["period"] == "week")

        # Daily assertions
        assert daily_item["limit"] == 50
        assert daily_item["count"] == 25
        assert daily_item["remaining"] == 25
        assert daily_item["percentage_used"] == 50.0

        # Weekly assertions
        assert weekly_item["limit"] == 200
        assert weekly_item["count"] == 75
        assert weekly_item["remaining"] == 125
        assert weekly_item["percentage_used"] == 37.5
