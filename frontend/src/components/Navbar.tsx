import React from 'react';
import { LogOut, BarChart2, Cpu, ShieldCheck } from 'lucide-react';
import { TenantId } from '../types';

interface NavbarProps {
  tenant: TenantId;
  userEmail?: string;
  userPhoto?: string;
  onSignOut: () => void;
  onSwitchCompany: () => void;
  onShowUsage?: () => void;
}

const Navbar: React.FC<NavbarProps> = ({
  tenant,
  userEmail,
  userPhoto,
  onSignOut,
  onSwitchCompany,
  onShowUsage,
}) => {
  const isAcme = tenant === 'acme';

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-4 sm:px-6 h-16 backdrop-blur-xl bg-[#0a0f1e]/80 border-b border-white/[0.06]">
      {/* Left: Logo */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onSwitchCompany}
          className="flex items-center p-1.5 -ml-1.5 rounded-xl hover:bg-white/[0.06] transition-all duration-200 group focus:outline-none"
          title="Return to Home Page"
        >
          <img
            src="/images/LOGO.png"
            alt="Multi-Tenant RAG"
            className="w-16 h-16 sm:w-20 sm:h-20 object-contain drop-shadow-lg group-hover:scale-105 transition-transform"
          />
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
            {isAcme ? <Cpu className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
          </div>
          <div className="hidden sm:block">
            <p className="text-xs font-semibold text-white/90 leading-tight">
              {isAcme ? 'Acme Corporation' : 'Globex Corporation'}
            </p>
            <p className={`text-[10px] font-medium tracking-widest uppercase leading-tight ${isAcme ? 'text-amber-400/70' : 'text-cyan-400/70'}`}>
              {isAcme ? 'Engineering Workspace' : 'Security Workspace'}
            </p>
          </div>
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        {onShowUsage && (
          <button
            onClick={onShowUsage}
            title="Usage & Limits"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white/60 hover:text-white/90 hover:bg-white/[0.06] transition-all duration-200 focus:outline-none"
          >
            <BarChart2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Usage</span>
          </button>
        )}

        {/* User Avatar */}
        {userPhoto ? (
          <img
            src={userPhoto}
            alt={userEmail || 'User'}
            className="w-7 h-7 rounded-full ring-1 ring-white/10 object-cover hidden sm:block"
          />
        ) : userEmail ? (
          <div className="w-7 h-7 rounded-full bg-white/10 flex items-center justify-center text-xs font-bold text-white/70 hidden sm:block">
            {userEmail[0].toUpperCase()}
          </div>
        ) : null}

        <button
          onClick={onSignOut}
          title="Sign Out"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white/60 hover:text-red-400 hover:bg-red-500/[0.08] transition-all duration-200 focus:outline-none"
        >
          <LogOut className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Sign Out</span>
        </button>
      </div>
    </nav>
  );
};

export default Navbar;
