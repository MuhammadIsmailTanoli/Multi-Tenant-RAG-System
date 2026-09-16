import React from 'react';
import { motion } from 'framer-motion';
import { Clock, ArrowLeft, OctagonX } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { RateLimitErrorDetail } from '../types';

interface RateLimitScreenProps {
  detail: RateLimitErrorDetail;
  onBackToChat: () => void;
}

export const RateLimitScreen: React.FC<RateLimitScreenProps> = ({
  detail,
  onBackToChat,
}) => {
  const { activeTenant, tokens } = useTheme();

  const resetFormatted = detail.reset_time
    ? new Date(detail.reset_time).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        timeZoneName: 'short',
      })
    : 'within 24 hours';

  const isWeekly =
    detail.limit?.toLowerCase().includes('week') ||
    detail.limit?.toLowerCase().includes('7 day');

  const isAcme = activeTenant === 'acme';
  const accentColor = isAcme ? 'amber' : 'cyan';
  const accentText = isAcme ? 'text-amber-400' : 'text-cyan-400';
  const accentBorder = isAcme ? 'border-amber-500/30' : 'border-cyan-500/30';
  const accentBg = isAcme ? 'bg-amber-500/10' : 'bg-cyan-500/10';
  const accentGlow = isAcme
    ? 'shadow-[0_0_60px_rgba(245,158,11,0.12)]'
    : 'shadow-[0_0_60px_rgba(6,182,212,0.12)]';

  return (
    <div className="relative min-h-screen flex flex-col justify-center items-center px-4 py-8 z-30">
      <motion.div
        initial={{ opacity: 0, scale: 0.92, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.92, y: 20 }}
        transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        className={`w-full max-w-xl p-8 sm:p-12 backdrop-blur-2xl bg-white/[0.04] border border-white/10 rounded-2xl ${accentGlow} relative overflow-hidden text-center`}
      >
        {/* Ambient glow blob */}
        <div
          className={`absolute top-0 left-1/2 -translate-x-1/2 w-80 h-48 rounded-full blur-3xl pointer-events-none ${accentBg} opacity-60`}
        />

        {/* Red alert orb */}
        <div className="absolute top-0 right-0 w-48 h-48 rounded-full blur-3xl pointer-events-none bg-red-500/[0.07]" />

        {/* Icon */}
        <motion.div
          initial={{ scale: 0.7, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.1, duration: 0.4 }}
          className="w-20 h-20 mx-auto mb-6 flex items-center justify-center rounded-2xl bg-red-500/10 border border-red-500/30 text-red-400"
        >
          <OctagonX className="w-10 h-10" />
        </motion.div>

        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mb-6"
        >
          <span
            className={`inline-block px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider mb-3 border ${accentBg} ${accentBorder} ${accentText}`}
          >
            HTTP 429 — Rate Limit Exceeded
          </span>
          <h2 className="text-2xl sm:text-3xl font-bold text-white mb-3 tracking-tight">
            Daily Quota Reached
          </h2>
          <p className="text-sm text-slate-300 max-w-md mx-auto leading-relaxed">
            You've hit the{' '}
            <span className="font-semibold text-white">
              {isWeekly ? 'weekly (200 query)' : 'daily (50 query)'}
            </span>{' '}
            limit tied to your Google identity. Limits are shared across{' '}
            <span className="font-semibold text-white">both companies</span> — switching
            to Globex or Acme won't reset your quota.
          </p>
        </motion.div>

        {/* Reset Info */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="flex items-center justify-center gap-2.5 p-4 rounded-xl bg-white/[0.03] border border-white/10 max-w-sm mx-auto mb-8 text-sm font-mono"
        >
          <Clock className={`w-4 h-4 shrink-0 ${accentText}`} />
          <span className="text-slate-200">
            Quota resets at:{' '}
            <span className={`font-bold ${accentText}`}>{resetFormatted}</span>
          </span>
        </motion.div>

        {/* Policy Details */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.25 }}
          className="mb-8 p-3.5 rounded-xl bg-white/[0.02] border border-white/8 text-xs text-slate-400 font-mono text-left space-y-1"
        >
          <div className="flex justify-between">
            <span className="text-slate-500">Period:</span>
            <span className="text-slate-200">{isWeekly ? 'Weekly (7 days)' : 'Daily (24 hours)'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Applied Policy:</span>
            <span className="text-slate-200">{detail.limit || 'Rate Limit Policy'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Scope:</span>
            <span className="text-slate-200">Acme Corp + Globex Corp combined</span>
          </div>
        </motion.div>

        {/* CTA */}
        <button
          type="button"
          onClick={onBackToChat}
          className="inline-flex items-center gap-2 px-6 py-3 text-sm font-semibold bg-white/[0.06] hover:bg-white/[0.10] text-slate-200 border border-white/15 hover:border-white/25 rounded-xl transition-all"
        >
          <ArrowLeft className="w-4 h-4" />
          Return to Chat
        </button>
      </motion.div>
    </div>
  );
};
