import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { AuthSession, GoogleUser, LimitsStatusResponse } from '../types';
import { loginCompany, switchCompany, fetchLimits } from '../utils/api';

interface AuthContextType {
  session: AuthSession | null;
  googleIdToken: string | null;
  googleUser: GoogleUser | null;
  limits: LimitsStatusResponse | null;
  isLoading: boolean;
  error: string | null;
  setGoogleAuth: (idToken: string, user: GoogleUser) => void;
  authenticateCompany: (
    tenantId: 'acme' | 'globex',
    password: string,
    explicitGoogleToken?: string
  ) => Promise<AuthSession>;
  switchCompanyAccess: (newTenantId: 'acme' | 'globex', password: string) => Promise<AuthSession>;
  refreshLimitsStatus: () => Promise<void>;
  logout: () => void;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType>({
  session: null,
  googleIdToken: null,
  googleUser: null,
  limits: null,
  isLoading: false,
  error: null,
  setGoogleAuth: () => {},
  authenticateCompany: async () => { throw new Error('Not implemented'); },
  switchCompanyAccess: async () => { throw new Error('Not implemented'); },
  refreshLimitsStatus: async () => {},
  logout: () => {},
  clearError: () => {},
});

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Session JWT is intentionally held strictly in React memory state (not localStorage)
  const [session, setSession] = useState<AuthSession | null>(null);
  const [googleIdToken, setGoogleIdToken] = useState<string | null>(() => {
    try {
      return localStorage.getItem('multi_tenant_rag_google_token') || null;
    } catch {
      return null;
    }
  });
  const [googleUser, setGoogleUser] = useState<GoogleUser | null>(() => {
    try {
      const saved = localStorage.getItem('multi_tenant_rag_google_user');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [limits, setLimits] = useState<LimitsStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const clearError = () => setError(null);

  const setGoogleAuth = (idToken: string, user: GoogleUser) => {
    try {
      localStorage.setItem('multi_tenant_rag_google_token', idToken);
      localStorage.setItem('multi_tenant_rag_google_user', JSON.stringify(user));
    } catch (e) {
      console.warn('Could not store Google auth in localStorage:', e);
    }
    setGoogleIdToken(idToken);
    setGoogleUser(user);
    setError(null);
  };

  const refreshLimitsStatus = useCallback(async () => {
    try {
      const data = await fetchLimits(session?.accessToken);
      setLimits(data);
    } catch (err) {
      console.warn('Failed to refresh limits:', err);
    }
  }, [session?.accessToken]);

  // Authenticate company with company password + Google ID token
  const authenticateCompany = async (
    tenantId: 'acme' | 'globex',
    password: string,
    explicitGoogleToken?: string
  ): Promise<AuthSession> => {
    const tokenToUse = explicitGoogleToken || googleIdToken;
    if (!tokenToUse) {
      throw new Error('Google authentication required before obtaining company session');
    }

    setIsLoading(true);
    setError(null);
    try {
      const newSession = await loginCompany(tenantId, password, tokenToUse);
      setSession(newSession);
      return newSession;
    } catch (err: any) {
      setError(err.message || 'Company authentication failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  // Switch company using existing client-held Google ID token and new password only
  const switchCompanyAccess = async (newTenantId: 'acme' | 'globex', password: string): Promise<AuthSession> => {
    if (!googleIdToken) {
      throw new Error('Google session expired. Please sign in with Google again.');
    }

    setIsLoading(true);
    setError(null);
    try {
      const newSession = await switchCompany(newTenantId, password, googleIdToken);
      setSession(newSession);
      return newSession;
    } catch (err: any) {
      setError(err.message || 'Company switch failed');
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    setSession(null);
    setGoogleIdToken(null);
    setGoogleUser(null);
    try {
      localStorage.removeItem('multi_tenant_rag_google_token');
      localStorage.removeItem('multi_tenant_rag_google_user');
    } catch {}
    setLimits(null);
    setError(null);
  };

  // Update limits on login
  useEffect(() => {
    if (session) {
      refreshLimitsStatus();
    }
  }, [session, refreshLimitsStatus]);

  return (
    <AuthContext.Provider
      value={{
        session,
        googleIdToken,
        googleUser,
        limits,
        isLoading,
        error,
        setGoogleAuth,
        authenticateCompany,
        switchCompanyAccess,
        refreshLimitsStatus,
        logout,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
