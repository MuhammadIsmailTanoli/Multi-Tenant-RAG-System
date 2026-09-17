import React, { createContext, useContext, useEffect, useState } from 'react';
import { TenantId } from '../types';

export interface ThemeTokens {
  tenantId: TenantId;
  name: string;
  fontFamily: string;
  bgClass: string;
  surfaceClass: string;
  cardClass: string;
  textClass: string;
  textMutedClass: string;
  primaryButtonClass: string;
  secondaryButtonClass: string;
  inputClass: string;
  borderClass: string;
  badgeClass: string;
  accentColor: string;
  accentGlow: string;
  motionTransition: any;
  cardRotation: string;
}

const acmeTokens: ThemeTokens = {
  tenantId: 'acme',
  name: 'Acme Corporation',
  fontFamily: 'font-sans',
  bgClass: 'bg-[#070A0F]',
  surfaceClass: 'bg-[#0D121F]',
  cardClass: 'backdrop-blur-2xl bg-white/[0.04] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] rounded-2xl',
  textClass: 'text-slate-100',
  textMutedClass: 'text-slate-400',
  primaryButtonClass: 'bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-semibold rounded-xl shadow-[0_0_20px_rgba(245,158,11,0.25)] active:scale-[0.98] transition-all',
  secondaryButtonClass: 'bg-white/[0.04] hover:bg-white/[0.08] text-amber-300 font-medium rounded-xl border border-amber-500/30 transition-all',
  inputClass: 'bg-white/[0.04] text-white placeholder-slate-500 border border-white/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-amber-500/30 focus:border-amber-500/50 transition-all',
  borderClass: 'border-amber-500/30',
  badgeClass: 'bg-amber-500/10 text-amber-300 border border-amber-500/25 rounded-full font-medium',
  accentColor: '#F59E0B',
  accentGlow: 'rgba(245, 158, 11, 0.25)',
  motionTransition: { duration: 0.25, ease: [0.16, 1, 0.3, 1] },
  cardRotation: 'rotate-0',
};

const globexTokens: ThemeTokens = {
  tenantId: 'globex',
  name: 'Globex Corporation',
  fontFamily: 'font-sans',
  bgClass: 'bg-[#070A0F]',
  surfaceClass: 'bg-[#0A111E]',
  cardClass: 'backdrop-blur-2xl bg-white/[0.04] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] rounded-2xl',
  textClass: 'text-slate-100',
  textMutedClass: 'text-slate-400',
  primaryButtonClass: 'bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold rounded-xl shadow-[0_0_20px_rgba(6,182,212,0.25)] active:scale-[0.98] transition-all',
  secondaryButtonClass: 'bg-white/[0.04] hover:bg-white/[0.08] text-cyan-300 font-medium rounded-xl border border-cyan-500/30 transition-all',
  inputClass: 'bg-white/[0.04] text-white placeholder-slate-500 border border-white/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-cyan-500/30 focus:border-cyan-500/50 transition-all',
  borderClass: 'border-cyan-500/30',
  badgeClass: 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/25 rounded-full font-medium',
  accentColor: '#06B6D4',
  accentGlow: 'rgba(6, 182, 212, 0.25)',
  motionTransition: { duration: 0.25, ease: [0.16, 1, 0.3, 1] },
  cardRotation: 'rotate-0',
};

const neutralTokens: ThemeTokens = {
  tenantId: null,
  name: 'Multi-Tenant System',
  fontFamily: 'font-sans',
  bgClass: 'bg-[#070A0F]',
  surfaceClass: 'bg-[#0E131F]',
  cardClass: 'backdrop-blur-2xl bg-white/[0.04] border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] rounded-2xl',
  textClass: 'text-slate-100',
  textMutedClass: 'text-slate-400',
  primaryButtonClass: 'bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 text-white font-semibold rounded-xl shadow-[0_0_20px_rgba(99,102,241,0.25)] transition-all',
  secondaryButtonClass: 'bg-white/[0.04] hover:bg-white/[0.08] text-slate-200 rounded-xl border border-white/10 transition-all',
  inputClass: 'bg-white/[0.04] text-white placeholder-slate-500 border border-white/10 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500/50 transition-all',
  borderClass: 'border-white/10',
  badgeClass: 'bg-white/10 text-slate-200 rounded-full',
  accentColor: '#6366F1',
  accentGlow: 'rgba(99, 102, 241, 0.25)',
  motionTransition: { duration: 0.25, ease: [0.16, 1, 0.3, 1] },
  cardRotation: 'rotate-0',
};

interface ThemeContextType {
  activeTenant: TenantId;
  tokens: ThemeTokens;
  setTheme: (tenant: TenantId) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  activeTenant: null,
  tokens: neutralTokens,
  setTheme: () => {},
});

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeTenant, setActiveTenant] = useState<TenantId>(null);

  const tokens = activeTenant === 'acme' 
    ? acmeTokens 
    : activeTenant === 'globex' 
      ? globexTokens 
      : neutralTokens;

  // Dynamically attach theme class to document body
  useEffect(() => {
    document.body.classList.remove('theme-acme', 'theme-globex', 'theme-neutral');
    document.body.style.backgroundColor = '#070A0F';
    document.body.style.color = '#F1F5F9';

    if (activeTenant === 'acme') {
      document.body.classList.add('theme-acme');
    } else if (activeTenant === 'globex') {
      document.body.classList.add('theme-globex');
    } else {
      document.body.classList.add('theme-neutral');
    }
  }, [activeTenant]);

  return (
    <ThemeContext.Provider value={{ activeTenant, tokens, setTheme: setActiveTenant }}>
      <div className={`${tokens.fontFamily} min-h-screen text-slate-100 bg-[#070A0F] transition-colors duration-300`}>
        {children}
      </div>
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
