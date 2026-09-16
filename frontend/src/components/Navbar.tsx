import React from 'react';
import { Cpu, ShieldCheck, Gauge, RefreshCw, LogOut, User } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';

interface NavbarProps {
  onOpenLimits?: () => void;
  onSwitchCompany: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  onSwitchCompany,
}) => {
  const { activeTenant, tokens } = useTheme();
  const { googleUser, logout } = useAuth();

  const isAcme = activeTenant === 'acme';

  return (
    <header className="sticky top-0 z-30 w-full backdrop-blur-xl bg-[#070A0F]/80 border-b border-white/8 shadow-[0_1px_24px_rgba(0,0,0,0.4)]">
      <div className="max-w-6xl mx-auto px-4 h-16 sm:h-[4.5rem] flex items-center justify-between gap-3">
        {/* Left: Platform Logo & Company Identity */}
        <div className="flex items-center gap-3 sm:gap-3.5">
          <button
            type="button"
            onClick={onSwitchCompany}
            className="flex items-center gap-2 p-1.5 -ml-1.5 rounded-xl hover:bg-white/[0.06] transition-all duration-200 group focus:outline-none"
            title="Return to Home Page"
          >
            <img
              src="/images/LOGO.png"
              alt="Multi-Tenant RAG"
              className="w-8 h-8 sm:w-9 sm:h-9 object-contain drop-shadow group-hover:scale-105 transition-transform"
            />
            <span className="hidden md:inline font-bold text-xs tracking-wider text-slate-300 group-hover:text-white uppercase font-mono">
              RAG // SYSTEM
            </span>
          </button>

          <div className="h-6 w-px bg-white/10 hidden sm:block" />

          {/* Company Identity */}
          <div className="flex items-center gap-2.5">
            <div
              className={`w-8 h-8 sm:w-9 sm:h-9 flex items-center justify-center shrink-0 rounded-xl border ${
                isAcme
                  ? 'bg-amber-500/10 border-amber-500/25 text-amber-400'
                  : 'bg-cyan-500/10 border-cyan-500/25 text-cyan-400'
              }`}
            >
              {isAcme ? <Cpu className="w-4 h-4 sm:w-5 sm:h-5" /> : <ShieldCheck className="w-4 h-4 sm:w-5 sm:h-5" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm sm:text-base font-bold text-white leading-none">
                  {isAcme ? 'Acme Corporation' : 'Globex Corporation'}
                </h1>
                <span
                  className={`hidden sm:inline-block text-[10px] px-2 py-0.5 font-semibold uppercase tracking-wider rounded-full border ${
                    isAcme
                      ? 'bg-amber-500/10 text-amber-300 border-amber-500/25'
                      : 'bg-cyan-500/10 text-cyan-300 border-cyan-500/25'
                  }`}
                >
                  {isAcme ? 'Policy AI' : 'Intel System'}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 hidden lg:block mt-0.5">
                {isAcme
                  ? 'Internal Knowledge Base · Handbook Retrieval'
                  : 'Enterprise Compliance · Security Intelligence'}
              </p>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 sm:gap-2.5">
          {/* Switch Company Button */}
          <button
            type="button"
            onClick={onSwitchCompany}
            className={`inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-xl transition-all ${tokens.primaryButtonClass}`}
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Switch Company</span>
          </button>

          {/* User Avatar & Logout */}
          <div className="flex items-center gap-2 pl-2 border-l border-white/10">
            {googleUser?.picture ? (
              <img
                src={googleUser.picture}
                alt={googleUser.name || 'User'}
                className={`w-8 h-8 rounded-full border ${
                  isAcme ? 'border-amber-500/40' : 'border-cyan-500/40'
                }`}
                title={googleUser.email}
              />
            ) : (
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold bg-white/10 text-white border border-white/15"
                title={googleUser?.email || 'User'}
              >
                <User className="w-4 h-4" />
              </div>
            )}

            <button
              type="button"
              onClick={logout}
              className="p-2 text-slate-400 hover:text-slate-200 transition-colors"
              title="Sign Out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
