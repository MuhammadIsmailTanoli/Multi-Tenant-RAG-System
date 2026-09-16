import React, { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, CheckCircle2, AlertCircle, Sparkles, ShieldCheck } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { verifyGoogleToken } from '../utils/api';

declare global {
  interface Window {
    google?: any;
  }
}

interface GoogleSignInStepProps {
  tenantId: 'acme' | 'globex';
  companyPassword: string;
  onSuccess: () => void;
  onBack: () => void;
}

export const GoogleSignInStep: React.FC<GoogleSignInStepProps> = ({
  tenantId,
  companyPassword,
  onSuccess,
  onBack,
}) => {
  const { tokens } = useTheme();
  const { setGoogleAuth, authenticateCompany } = useAuth();
  const [isVerifying, setIsVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [googleClientLoaded, setGoogleClientLoaded] = useState(false);
  const gsiContainerRef = useRef<HTMLDivElement>(null);

  // Default client ID configured in backend .env
  const googleClientId =
    '329878057926-7b1n7jk22m4hd2ergntsrt2rda79k0f5.apps.googleusercontent.com';

  const handleCredentialResponse = async (credentialResponse: any) => {
    const idToken = credentialResponse.credential;
    if (!idToken) {
      setErrorMessage('No credential received from Google Sign-In.');
      return;
    }

    setIsVerifying(true);
    setErrorMessage(null);

    try {
      // 1. Verify Google identity with backend
      const googleUser = await verifyGoogleToken(idToken);
      setGoogleAuth(idToken, googleUser);

      // 2. Complete combined company session flow with verified idToken
      await authenticateCompany(tenantId, companyPassword, idToken);

      // 3. Proceed to chat interface
      onSuccess();
    } catch (err: any) {
      console.error('Authentication error:', err);
      setErrorMessage(err.message || 'Google identity verification failed.');
    } finally {
      setIsVerifying(false);
    }
  };

  // Render Google Identity Services button
  useEffect(() => {
    let checkInterval: any = null;

    const tryInitGSI = () => {
      if (window.google?.accounts?.id && gsiContainerRef.current) {
        setGoogleClientLoaded(true);
        try {
          window.google.accounts.id.initialize({
            client_id: googleClientId,
            callback: handleCredentialResponse,
            auto_select: false,
          });

          gsiContainerRef.current.innerHTML = '';
          window.google.accounts.id.renderButton(gsiContainerRef.current, {
            theme: 'filled_black',
            size: 'large',
            width: 320,
            text: 'signin_with',
            shape: 'pill',
          });
        } catch (e) {
          console.warn('Google GSI button rendering error:', e);
        }
        return true;
      }
      return false;
    };

    if (!tryInitGSI()) {
      checkInterval = setInterval(() => {
        if (tryInitGSI()) {
          clearInterval(checkInterval);
        }
      }, 300);
    }

    return () => {
      if (checkInterval) clearInterval(checkInterval);
    };
  }, [tenantId]);

  return (
    <div className="relative min-h-screen flex flex-col justify-center items-center px-4 py-8 z-10">
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md p-8 sm:p-10 backdrop-blur-2xl bg-white/[0.03] border border-white/10 rounded-2xl shadow-[0_8px_40px_rgba(0,0,0,0.5)] relative overflow-hidden"
      >
        {/* Subtle accent glow */}
        <div
          className={`absolute top-0 right-0 w-56 h-56 rounded-full blur-3xl pointer-events-none opacity-50 ${
            tenantId === 'acme' ? 'bg-amber-500/10' : 'bg-cyan-500/10'
          }`}
        />

        {/* Back Button */}
        <button
          type="button"
          onClick={onBack}
          disabled={isVerifying}
          className="inline-flex items-center gap-1.5 text-xs font-medium mb-8 text-slate-400 hover:text-slate-200 transition-colors disabled:opacity-50"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Password Entry
        </button>

        {/* Step Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-3">
            <div
              className={`w-11 h-11 flex items-center justify-center rounded-2xl border ${
                tenantId === 'acme'
                  ? 'bg-amber-500/10 border-amber-500/25 text-amber-400'
                  : 'bg-cyan-500/10 border-cyan-500/25 text-cyan-400'
              }`}
            >
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-0.5">
                Step 2 of 2 — Identity Verification
              </span>
              <h2 className="text-xl font-bold text-white">
                Google Sign-In
              </h2>
            </div>
          </div>
          <p className="text-sm text-slate-400 leading-relaxed">
            Sign in with Google to bind your session to a verified identity. Rate limits are tracked per Google account across both companies.
          </p>
        </div>

        {/* Error Alert */}
        <AnimatePresence>
          {errorMessage && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="mb-6 p-3.5 bg-red-950/50 border border-red-500/30 text-red-300 text-xs font-medium rounded-xl flex items-center gap-2.5"
            >
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{errorMessage}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Verifying Spinner */}
        {isVerifying ? (
          <div className="py-10 flex flex-col items-center justify-center text-center gap-4">
            <div className="flex justify-center items-center gap-2.5">
              <motion.div
                className={`w-3 h-3 rounded-full ${tenantId === 'acme' ? 'bg-amber-400' : 'bg-cyan-400'}`}
                animate={{ y: [0, -10, 0], opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 0.6, repeat: Infinity }}
              />
              <motion.div
                className={`w-3 h-3 rounded-full ${tenantId === 'acme' ? 'bg-amber-400' : 'bg-cyan-400'}`}
                animate={{ y: [0, -10, 0], opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 0.6, repeat: Infinity, delay: 0.15 }}
              />
              <motion.div
                className={`w-3 h-3 rounded-full ${tenantId === 'acme' ? 'bg-amber-400' : 'bg-cyan-400'}`}
                animate={{ y: [0, -10, 0], opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 0.6, repeat: Infinity, delay: 0.3 }}
              />
            </div>
            <div>
              <p className="text-sm font-semibold text-white mb-1">Verifying identity...</p>
              <p className="text-xs text-slate-400">Issuing signed session token</p>
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            {/* Google Sign-In Button Container */}
            <div className="p-5 rounded-xl flex flex-col items-center justify-center min-h-[90px] bg-white/[0.03] border border-white/10">
              <div ref={gsiContainerRef} className="flex justify-center" />
              {!googleClientLoaded && (
                <p className="text-xs text-slate-500 animate-pulse mt-2">
                  Initializing Google Sign-In...
                </p>
              )}
            </div>

            {/* Security note */}
            <div className="flex items-start gap-2">
              <CheckCircle2
                className={`w-4 h-4 shrink-0 mt-0.5 ${
                  tenantId === 'acme' ? 'text-amber-400' : 'text-cyan-400'
                }`}
              />
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Your session token is held in React memory only and never persisted to localStorage. Rate limits are tied to your Google Sub ID across both companies.
              </p>
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
};
