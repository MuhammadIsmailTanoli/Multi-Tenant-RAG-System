import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { KeyRound, ArrowLeft, AlertCircle, ShieldCheck, Lock, Eye, EyeOff } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

interface PasswordGateProps {
  tenantId: 'acme' | 'globex';
  onSuccess: (password: string) => void;
  onBack: () => void;
}

export const PasswordGate: React.FC<PasswordGateProps> = ({
  tenantId,
  onSuccess,
  onBack,
}) => {
  const { tokens } = useTheme();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isShaking, setIsShaking] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const expectedPassword = tenantId === 'acme' ? 'Acme@Admin' : 'Globex@Admin';
  const accentColor = tenantId === 'acme' ? 'amber' : 'cyan';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) {
      setError('Please enter the company password.');
      triggerErrorAnimation();
      return;
    }

    if (password !== expectedPassword) {
      setError('Invalid company password. Please check your credentials and try again.');
      triggerErrorAnimation();
      return;
    }

    setError(null);
    onSuccess(password);
  };

  const triggerErrorAnimation = () => {
    setIsShaking(true);
    setTimeout(() => setIsShaking(false), 600);
  };

  return (
    <div className="relative min-h-screen flex flex-col justify-center items-center px-4 py-8 z-10">
      {/* Top Left Logo linking back to 1st home page */}
      <motion.div
        initial={{ opacity: 0, x: -10 }}
        animate={{ opacity: 1, x: 0 }}
        className="fixed top-5 left-5 sm:top-6 sm:left-6 z-40 cursor-pointer flex items-center gap-2.5 px-3 py-2 rounded-2xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 backdrop-blur-xl shadow-lg transition-all duration-200 group"
        onClick={onBack}
        title="Return to Home Page"
      >
        <img
          src="/images/LOGO.png"
          alt="Multi-Tenant RAG"
          className="w-8 h-8 sm:w-9 sm:h-9 object-contain drop-shadow group-hover:scale-105 transition-transform"
        />
        <span className="font-bold text-xs tracking-wider text-slate-300 group-hover:text-white uppercase font-mono hidden sm:inline">
          RAG // SYSTEM
        </span>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 20 }}
        animate={
          isShaking
            ? { x: [-12, 12, -10, 10, -6, 6, -2, 2, 0], scale: 1, y: 0, opacity: 1,
                transition: { duration: 0.5 } }
            : { opacity: 1, scale: 1, y: 0, x: 0 }
        }
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
          className="inline-flex items-center gap-1.5 text-xs font-medium mb-8 text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Company Selector
        </button>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-3">
            <div
              className={`w-11 h-11 flex items-center justify-center rounded-2xl border ${
                tenantId === 'acme'
                  ? 'bg-amber-500/10 border-amber-500/25 text-amber-400'
                  : 'bg-cyan-500/10 border-cyan-500/25 text-cyan-400'
              }`}
            >
              <KeyRound className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-0.5">
                Step 1 of 2 — Access Control
              </span>
              <h2 className="text-xl font-bold text-white">
                {tenantId === 'acme' ? 'Acme Corp Password' : 'Globex Authorization Code'}
              </h2>
            </div>
          </div>
          <p className="text-sm text-slate-400 leading-relaxed">
            {tenantId === 'acme'
              ? 'Enter the Acme Corporation workspace password to proceed.'
              : 'Enter the Globex Corporation access code to proceed.'}
          </p>
        </div>

        {/* Error Alert */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              className="mb-5 p-3.5 bg-red-950/50 border border-red-500/30 text-red-300 text-xs font-medium rounded-xl flex items-center gap-2.5"
            >
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
              <span>{error}</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Password Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label
              htmlFor="company-password"
              className="block text-xs font-semibold mb-2 text-slate-300 uppercase tracking-wider"
            >
              Company Password
            </label>
            <div className="relative">
              <input
                id="company-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter company password..."
                autoFocus
                className="w-full px-4 py-3 pr-10 text-sm bg-white/[0.04] text-white placeholder-slate-500 border border-white/10 rounded-xl focus:outline-none focus:ring-2 focus:border-transparent transition-all"
                style={{
                  ['--tw-ring-color' as any]: tenantId === 'acme'
                    ? 'rgba(245,158,11,0.3)'
                    : 'rgba(6,182,212,0.3)',
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3.5 top-3.5 text-slate-400 hover:text-slate-200 transition-colors"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className={`w-full py-3.5 px-4 text-sm font-semibold flex items-center justify-center gap-2 rounded-xl transition-all ${
              tenantId === 'acme'
                ? 'bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 shadow-[0_0_20px_rgba(245,158,11,0.2)]'
                : 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white shadow-[0_0_20px_rgba(6,182,212,0.2)]'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            Verify Password & Continue
          </button>
        </form>
      </motion.div>
    </div>
  );
};
