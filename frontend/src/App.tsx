import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import { BackgroundAmbient } from './components/BackgroundAmbient';
import { LandingPage } from './components/LandingPage';
import { PasswordGate } from './components/PasswordGate';
import { GoogleSignInStep } from './components/GoogleSignInStep';
import { ChatPage } from './components/ChatPage';
import { Navbar } from './components/Navbar';
import { LimitsModal } from './components/LimitsModal';
import { RateLimitScreen } from './components/RateLimitScreen';
import { AppScreen, RateLimitErrorDetail } from './types';

// Inner app reads from ThemeContext and AuthContext
const InnerApp: React.FC = () => {
  const { activeTenant, setTheme } = useTheme();
  const { session, googleIdToken, switchCompanyAccess, authenticateCompany } = useAuth();

  const [screen, setScreen] = useState<AppScreen>('landing');
  const [pendingTenant, setPendingTenant] = useState<'acme' | 'globex' | null>(null);
  const [companyPassword, setCompanyPassword] = useState('');
  const [showLimitsModal, setShowLimitsModal] = useState(false);
  const [rateLimitDetail, setRateLimitDetail] = useState<RateLimitErrorDetail | null>(null);

  const handleSelectCompany = (tenant: 'acme' | 'globex') => {
    setPendingTenant(tenant);
    setTheme(tenant);
    setScreen('password');
  };

  const handlePasswordSuccess = async (password: string) => {
    setCompanyPassword(password);

    // If user already has a Google token (either in session or remembered), authenticate directly without asking for Google Sign-In again
    if (googleIdToken) {
      try {
        if (session) {
          await switchCompanyAccess(pendingTenant!, password);
        } else {
          await authenticateCompany(pendingTenant!, password, googleIdToken);
        }
        setScreen('chat');
        return;
      } catch (err) {
        console.warn('Authentication with remembered Google token failed, requesting re-auth:', err);
        setScreen('google-auth');
        return;
      }
    }

    setScreen('google-auth');
  };

  const handleGoogleAuthSuccess = () => {
    setScreen('chat');
  };

  const handleSwitchCompany = () => {
    setTheme(null);
    setScreen('landing');
  };

  const handleRateLimitHit = (detail: RateLimitErrorDetail) => {
    setRateLimitDetail(detail);
    setScreen('rate-limit');
  };

  const handleBackToChat = () => {
    setRateLimitDetail(null);
    setScreen('chat');
  };

  // Page transition variants
  const pageVariants = {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -12 },
  };

  const pageTransition = activeTenant === 'globex'
    ? { type: 'tween', ease: 'linear', duration: 0.15 }
    : { type: 'spring', bounce: 0.3, duration: 0.45 };

  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Ambient background always rendered behind content */}
      <BackgroundAmbient />

      {/* Limits Modal (portal-style overlay) */}
      {showLimitsModal && (
        <LimitsModal isOpen={showLimitsModal} onClose={() => setShowLimitsModal(false)} />
      )}

      {/* Navbar only shown when in chat */}
      {screen === 'chat' && (
        <Navbar
          onOpenLimits={() => setShowLimitsModal(true)}
          onSwitchCompany={handleSwitchCompany}
          onSignOut={handleSwitchCompany}
        />
      )}

      {/* Main Screen Router with AnimatePresence for smooth transitions */}
      <AnimatePresence mode="wait">
        {screen === 'landing' && (
          <motion.div
            key="landing"
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={pageTransition}
          >
            <LandingPage onSelectCompany={handleSelectCompany} />
          </motion.div>
        )}

        {screen === 'password' && pendingTenant && (
          <motion.div
            key="password"
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={pageTransition}
          >
            <PasswordGate
              tenantId={pendingTenant}
              onSuccess={handlePasswordSuccess}
              onBack={() => {
                setTheme(null);
                setScreen('landing');
              }}
            />
          </motion.div>
        )}

        {screen === 'google-auth' && pendingTenant && (
          <motion.div
            key="google-auth"
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={pageTransition}
          >
            <GoogleSignInStep
              tenantId={pendingTenant}
              companyPassword={companyPassword}
              onSuccess={handleGoogleAuthSuccess}
              onBack={() => setScreen('password')}
              onHome={() => {
                setTheme(null);
                setScreen('landing');
              }}
            />
          </motion.div>
        )}

        {screen === 'chat' && (
          <motion.div
            key={`chat-${activeTenant}`}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={pageTransition}
          >
            <ChatPage
              onRateLimitHit={handleRateLimitHit}
              onOpenLimits={() => setShowLimitsModal(true)}
            />
          </motion.div>
        )}

        {screen === 'rate-limit' && rateLimitDetail && (
          <motion.div
            key="rate-limit"
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={pageTransition}
          >
            <RateLimitScreen
              detail={rateLimitDetail}
              onBackToChat={handleBackToChat}
              onHome={handleSwitchCompany}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

// Root App wraps with ThemeProvider and AuthProvider
const App: React.FC = () => {
  return (
    <ThemeProvider>
      <AuthProvider>
        <InnerApp />
      </AuthProvider>
    </ThemeProvider>
  );
};

export default App;
