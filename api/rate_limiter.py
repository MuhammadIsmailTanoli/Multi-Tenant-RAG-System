"""Persistent SQLite-backed rate limiting keyed by Google user identity.

Enforces per-user query rate limits (e.g. 50 requests/day, 200 requests/week)
keyed strictly by the user's permanent Google identity (google_sub claim from JWT),
ensuring rate limits span both Acme Corp and Globex Corporation combined.
"""

from __future__ import annotations

import datetime
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Tuple

import limits.storage
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from ingestion.config import get_settings, PROJECT_ROOT
from api.auth import decode_tenant_token

logger = logging.getLogger("api.rate_limiter")
settings = get_settings()


class SQLiteStorage(limits.storage.Storage):
    """Custom SQLite-backed storage backend for limits and slowapi.

    Persists hit counters and window expirations across server restarts.
    """

    STORAGE_SCHEME = ["sqlite"]

    def __init__(
        self,
        uri: str,
        wrap_exceptions: bool = False,
        **options,
    ) -> None:
        super().__init__(uri, wrap_exceptions, **options)
        self.lock = threading.Lock()

        # Parse SQLite file path from URI (e.g. sqlite:///data/rate_limits.db or sqlite://:memory:)
        parsed = urlparse(uri)
        path_str = parsed.path
        if parsed.netloc:
            path_str = parsed.netloc + path_str

        # Remove leading slashes
        clean_path = path_str.lstrip("/")
        if not clean_path or clean_path == ":memory:":
            self.db_path = ":memory:"
        else:
            db_p = Path(clean_path)
            if not db_p.is_absolute():
                db_p = (PROJECT_ROOT / db_p).resolve()
            # Ensure parent directory exists
            db_p.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(db_p)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the rate limits schema if not already present."""
        with self.lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limits (
                    key TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    expires_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rate_limits_expires
                ON rate_limits (expires_at)
                """
            )
            self._conn.commit()

    @property
    def base_exceptions(self) -> Tuple[type[Exception], ...]:
        return (sqlite3.Error, OSError)

    def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        """Increment the counter for a given rate limit key, resetting on expiration."""
        now = time.time()
        with self.lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT count, expires_at FROM rate_limits WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()

            if row is None or row[1] <= now:
                new_count = amount
                expires_at = now + expiry
                cur.execute(
                    "INSERT OR REPLACE INTO rate_limits (key, count, expires_at) VALUES (?, ?, ?)",
                    (key, new_count, expires_at),
                )
            else:
                new_count = row[0] + amount
                cur.execute(
                    "UPDATE rate_limits SET count = ? WHERE key = ?",
                    (new_count, key),
                )
            self._conn.commit()
            return new_count

    def get(self, key: str) -> int:
        """Get the current count for a key, returning 0 if expired."""
        now = time.time()
        with self.lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT count, expires_at FROM rate_limits WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
            if row is None:
                return 0
            if row[1] <= now:
                cur.execute("DELETE FROM rate_limits WHERE key = ?", (key,))
                self._conn.commit()
                return 0
            return row[0]

    def get_expiry(self, key: str) -> float:
        """Get the timestamp when the current window expires."""
        now = time.time()
        with self.lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT expires_at FROM rate_limits WHERE key = ?",
                (key,),
            )
            row = cur.fetchone()
            if row is None or row[0] <= now:
                return now
            return float(row[0])

    def check(self) -> bool:
        """Verify storage connectivity and health."""
        try:
            with self.lock:
                self._conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    def reset(self) -> int:
        """Clear all rate limit entries from SQLite storage."""
        with self.lock:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM rate_limits")
            cnt = cur.fetchone()[0]
            cur.execute("DELETE FROM rate_limits")
            self._conn.commit()
            return cnt

    def clear(self, key: str) -> None:
        """Clear a specific rate limit key."""
        with self.lock:
            self._conn.execute("DELETE FROM rate_limits WHERE key = ?", (key,))
            self._conn.commit()


def get_google_sub_key(request: Request) -> str:
    """Extract rate limit key based strictly on the user's permanent Google identity (google_sub).

    If the request has a valid Bearer token containing a 'google_sub' claim,
    that claim is used as the key. As a result, requests across both Acme and Globex
    count towards the same single quota for the real user.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        raw_token = auth_header[7:].strip()
        try:
            payload = decode_tenant_token(raw_token)
            google_sub = payload.get("google_sub")
            if google_sub and str(google_sub).strip():
                return f"google_user:{str(google_sub).strip()}"
        except Exception as e:
            logger.debug(f"Failed to extract google_sub for rate limiting key: {e}")

    # Fallback to IP address for unauthenticated requests before 401 rejection
    return f"unauthenticated:{get_remote_address(request)}"


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return an informative HTTP 429 response when daily or weekly rate limits are exceeded."""
    now = time.time()
    reset_epoch = None
    reset_time_iso = None
    retry_after_seconds = 60

    if hasattr(request.state, "view_rate_limit") and request.state.view_rate_limit:
        try:
            item, args = request.state.view_rate_limit
            stats = request.app.state.limiter.limiter.get_window_stats(item, *args)
            reset_epoch = int(stats.reset_time)
            retry_after_seconds = max(1, int(stats.reset_time - now))
            reset_time_iso = datetime.datetime.fromtimestamp(
                reset_epoch, tz=datetime.timezone.utc
            ).isoformat()
        except Exception as e:
            logger.warning(f"Error calculating rate limit reset time: {e}")

    logger.warning(
        f"Rate limit exceeded on {request.url.path}: {exc.detail}. "
        f"Retry after: {retry_after_seconds}s (reset: {reset_time_iso})"
    )

    headers = {
        "Retry-After": str(retry_after_seconds),
    }
    if reset_epoch:
        headers["X-RateLimit-Reset"] = str(reset_epoch)

    return JSONResponse(
        status_code=429,
        content={
            "detail": f"Rate limit exceeded: {exc.detail}. Real user query limit reached across all companies.",
            "limit": str(exc.detail),
            "reset_time": reset_time_iso,
            "reset_epoch": reset_epoch,
            "retry_after_seconds": retry_after_seconds,
        },
        headers=headers,
    )


# Instantiate application limiter with SQLite storage and google_sub key function
limiter = Limiter(
    key_func=get_google_sub_key,
    storage_uri=settings.rate_limit_storage_uri,
    enabled=settings.rate_limit_enabled,
)


def get_user_limits_status(google_sub: Optional[str] = None) -> dict:
    """Retrieve current query rate limit usage, remaining counts, and reset times for a Google user."""
    from limits import parse_many

    limit_items = parse_many(settings.rate_limit_query)
    now = time.time()
    scope = "/query"

    stats_list = []
    for item in limit_items:
        limit_amount = item.amount
        granularity = getattr(item, "GRANULARITY", None)
        secs = getattr(granularity, "seconds", 86400) if granularity else 86400
        mult = getattr(item, "multiples", 1)
        granularity_seconds = int(secs * mult)
        period_name = "day" if granularity_seconds == 86400 else ("week" if granularity_seconds == 604800 else f"{granularity_seconds}s")

        if google_sub and str(google_sub).strip():
            user_key = f"google_user:{str(google_sub).strip()}"
            key = item.key_for(user_key, scope)
            count = limiter._storage.get(key)
            expiry = limiter._storage.get_expiry(key)
        else:
            count = 0
            expiry = 0.0

        remaining = max(0, limit_amount - count)
        reset_seconds = max(0, int(expiry - now)) if count > 0 and expiry > now else 0
        reset_time_iso = (
            datetime.datetime.fromtimestamp(int(expiry), tz=datetime.timezone.utc).isoformat()
            if count > 0 and expiry > now
            else None
        )
        percentage = round((count / limit_amount) * 100, 1) if limit_amount > 0 else 0.0

        stats_list.append({
            "limit": limit_amount,
            "period": period_name,
            "granularity_seconds": granularity,
            "count": count,
            "remaining": remaining,
            "percentage_used": percentage,
            "reset_seconds": reset_seconds,
            "reset_time": reset_time_iso,
        })

    return {
        "google_sub": google_sub if google_sub else None,
        "authenticated": bool(google_sub and str(google_sub).strip()),
        "limits": stats_list,
    }
