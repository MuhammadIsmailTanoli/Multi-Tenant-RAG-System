export type TenantId = 'acme' | 'globex' | null;

export interface TenantInfo {
  id: 'acme' | 'globex';
  name: string;
  tagline: string;
  description: string;
  mascotOrCode: string;
  sampleQuestion: string;
}

export interface GoogleUser {
  sub: string;
  email: string;
  name?: string;
  picture?: string;
}

export interface AuthSession {
  accessToken: string;
  tenantId: 'acme' | 'globex';
  googleSub: string;
  email?: string;
  expiresIn: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  tenantId: 'acme' | 'globex';
  isError?: boolean;
}

export interface LimitMetric {
  limit: number;
  period: string;
  count: number;
  remaining: number;
  percentage_used: number;
  reset_seconds: number;
  reset_time: string | null;
}

export interface LimitsStatusResponse {
  google_sub: string | null;
  authenticated: boolean;
  limits: LimitMetric[];
}

export interface RateLimitErrorDetail {
  detail: string;
  limit: string;
  reset_time: string | null;
  reset_epoch?: number;
  retry_after_seconds: number;
}

export type AppScreen = 'landing' | 'password' | 'google-auth' | 'chat' | 'rate-limit';
