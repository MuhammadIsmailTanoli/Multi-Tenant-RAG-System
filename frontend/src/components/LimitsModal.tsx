import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, RefreshCw, Gauge, ShieldCheck, Clock, CheckCircle, TrendingUp } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';

interface LimitsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const LimitsModal: React.FC<LimitsModalProps> = ({ isOpen, onClose }) => {
  const { activeTenant, tokens } = useTheme();
  const { limits, refreshLimitsStatus, googleUser } = useAuth();
  const [isRefreshing, setIsRefreshing] = React.useState(false);

  if (!isOpen) return null;

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await refreshLimitsStatus();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  const dailyMetric = limits?.limits?.find((item) => item.period === 'day') || {
    limit: 50,
    count: 0,
    remaining: 50,
    percentage_used: 0,
    reset_seconds: 0,
    reset_time: null,
  };

  const weeklyMetric = limits?.limits?.find((item) => item.period === 'week') || {
    limit: 200,
    count: 0,
    remaining: 200,
    percentage_used: 0,
    reset_seconds: 0,
    reset_time: null,
  };

  const getBarColor = (pct: number) => {
    if (pct < 60) return activeTenant === 'acme'
      ? 'from-amber-500 to-yellow-400'
      : 'from-cyan-500 to-blue-400';
    if (pct <= 85) return 'from-orange-400 to-amber-500';
    return 'from-rose-500 to-red-600';
  };

  const formatSeconds = (seconds: number) => {
    if (!seconds || seconds <= 0) return 'Active window';
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hours > 0) return `Resets in ~${hours}h ${mins}m`;
    return `Resets in ~${mins}m`;
  };

  const accentText = activeTenant === 'acme' ? 'text-amber-400' : 'text-cyan-400';
  const accentBorder = activeTenant === 'acme' ? 'border-amber-500/30' : 'border-cyan-500/30';
  const accentBg = activeTenant === 'acme' ? 'bg-amber-500/10' : 'bg-cyan-500/10';

  return (
    <AnimatePresence>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 15 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-lg p-6 sm:p-8 backdrop-blur-2xl bg-white/[0.04] border border-white/10 rounded-2xl shadow-[0_24px_64px_rgba(0,0,0,0.6)] relative overflow-hidden"
        >
          {/* Ambient glow */}
          <div className={`absolute top-0 right-0 w-48 h-48 rounded-full blur-3xl pointer-events-none opacity-40 ${accentBg}`} />

          {/* Header */}
          <div className="flex items-center justify-between pb-5 border-b border-white/10 mb-6">
            <div className="flex items-center gap-2.5">
              <div className={`w-9 h-9 flex items-center justify-center rounded-xl border ${accentBg} ${accentBorder} ${accentText}`}>
                <Gauge className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white">Usage & Rate Limits</h3>
                <p className="text-[11px] text-slate-400">
                  Tracked per Google identity across both companies
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-white/10 transition-all"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* User Identity Banner */}
          <div className="p-3.5 rounded-xl mb-6 bg-white/[0.02] border border-white/8 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
              <span className="font-mono text-[11px] text-slate-200">
                {googleUser?.email || 'Authenticated Session'}
              </span>
            </div>
            <span className="text-[10px] uppercase font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
              SQLite Active
            </span>
          </div>

          {/* Quota Cards */}
          <div className="space-y-4">
            {/* Daily Quota */}
            <div className="p-4 sm:p-5 rounded-xl bg-white/[0.02] border border-white/8">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5" />
                  Daily Quota
                </span>
                <div className="text-right">
                  <span className="text-lg font-bold text-white">{dailyMetric.count}</span>
                  <span className="text-sm text-slate-400"> / {dailyMetric.limit}</span>
                  <span className={`ml-1.5 text-xs font-semibold ${accentText}`}>
                    ({dailyMetric.percentage_used}%)
                  </span>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="w-full h-2.5 bg-white/[0.06] rounded-full overflow-hidden mb-3">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(100, dailyMetric.percentage_used)}%` }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                  className={`h-full rounded-full bg-gradient-to-r ${getBarColor(dailyMetric.percentage_used)}`}
                />
              </div>

              <div className="flex items-center justify-between text-[11px]">
                <span className="text-emerald-400 font-medium flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  {dailyMetric.remaining} remaining
                </span>
                <span className="text-slate-500 flex items-center gap-1 font-mono">
                  <Clock className="w-3 h-3" />
                  {formatSeconds(dailyMetric.reset_seconds)}
                </span>
              </div>
            </div>

            {/* Weekly Quota */}
            <div className="p-4 sm:p-5 rounded-xl bg-white/[0.02] border border-white/8">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5" />
                  Weekly Quota
                </span>
                <div className="text-right">
                  <span className="text-lg font-bold text-white">{weeklyMetric.count}</span>
                  <span className="text-sm text-slate-400"> / {weeklyMetric.limit}</span>
                  <span className={`ml-1.5 text-xs font-semibold ${accentText}`}>
                    ({weeklyMetric.percentage_used}%)
                  </span>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="w-full h-2.5 bg-white/[0.06] rounded-full overflow-hidden mb-3">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.min(100, weeklyMetric.percentage_used)}%` }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                  className={`h-full rounded-full bg-gradient-to-r ${getBarColor(weeklyMetric.percentage_used)}`}
                />
              </div>

              <div className="flex items-center justify-between text-[11px]">
                <span className="text-emerald-400 font-medium flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  {weeklyMetric.remaining} remaining
                </span>
                <span className="text-slate-500 flex items-center gap-1 font-mono">
                  <Clock className="w-3 h-3" />
                  {formatSeconds(weeklyMetric.reset_seconds)}
                </span>
              </div>
            </div>
          </div>

          {/* Footer Controls */}
          <div className="mt-6 flex items-center justify-between pt-5 border-t border-white/10">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 border border-white/10 transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>

            <button
              type="button"
              onClick={onClose}
              className={`px-5 py-2 text-xs font-semibold rounded-xl transition-all ${tokens.primaryButtonClass}`}
            >
              Close
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
