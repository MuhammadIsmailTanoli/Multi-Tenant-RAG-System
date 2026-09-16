import { AuthSession, GoogleUser, LimitsStatusResponse, RateLimitErrorDetail } from '../types';

/**
 * Custom error class capturing rate limit details when HTTP 429 is returned.
 */
export class RateLimitError extends Error {
  detail: RateLimitErrorDetail;

  constructor(detail: RateLimitErrorDetail) {
    super(detail.detail || 'Rate limit exceeded');
    this.name = 'RateLimitError';
    this.detail = detail;
  }
}

/**
 * Verify Google OAuth 2.0 ID Token with backend.
 */
export async function verifyGoogleToken(idToken: string): Promise<GoogleUser> {
  const response = await fetch('/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id_token: idToken }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to verify Google Identity');
  }

  const data = await response.json();
  return {
    sub: data.google_user_id,
    email: data.email,
    name: data.name,
    picture: data.picture,
  };
}

/**
 * Authenticate with company password and Google ID token.
 */
export async function loginCompany(
  tenantId: 'acme' | 'globex',
  password: string,
  googleIdToken: string
): Promise<AuthSession> {
  const response = await fetch('/auth/company', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_id: tenantId,
      password,
      google_id_token: googleIdToken,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Authentication failed');
  }

  const data = await response.json();
  return {
    accessToken: data.access_token,
    tenantId: data.tenant_id,
    googleSub: data.google_sub,
    email: data.email,
    expiresIn: data.expires_in,
  };
}

/**
 * Switch company using existing client-held Google ID token and new password.
 */
export async function switchCompany(
  newTenantId: 'acme' | 'globex',
  password: string,
  googleIdToken: string
): Promise<AuthSession> {
  const response = await fetch('/auth/switch-company', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      new_tenant_id: newTenantId,
      password,
      google_id_token: googleIdToken,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to switch company');
  }

  const data = await response.json();
  return {
    accessToken: data.access_token,
    tenantId: data.tenant_id,
    googleSub: data.google_sub,
    email: data.email,
    expiresIn: data.expires_in,
  };
}

/**
 * Query handbook grounded in tenant document context.
 */
export async function queryHandbook(
  tenantId: 'acme' | 'globex',
  question: string,
  token: string
): Promise<{ answer: string; chunksRetrieved: number; executionTimeMs: number }> {
  const response = await fetch('/query', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      tenant_id: tenantId,
      question,
      top_k: 4,
    }),
  });

  if (response.status === 429) {
    const errorData = await response.json().catch(() => ({}));
    throw new RateLimitError({
      detail: errorData.detail || 'Rate limit reached',
      limit: errorData.limit || 'Quota exceeded',
      reset_time: errorData.reset_time || null,
      reset_epoch: errorData.reset_epoch,
      retry_after_seconds: errorData.retry_after_seconds || 60,
    });
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `Query failed with status ${response.status}`);
  }

  const data = await response.json();
  return {
    answer: data.answer || 'No answer returned.',
    chunksRetrieved: data.chunks_retrieved || 0,
    executionTimeMs: data.execution_time_ms || 0,
  };
}

/**
 * Fetch current rate limit usage stats.
 */
export async function fetchLimits(token?: string): Promise<LimitsStatusResponse> {
  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch('/limits', {
    headers,
  });

  if (!response.ok) {
    throw new Error('Failed to fetch rate limits');
  }

  return response.json();
}
