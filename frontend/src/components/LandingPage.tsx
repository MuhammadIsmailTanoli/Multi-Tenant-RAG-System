import React, { useState, useEffect } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import Tilt from 'react-parallax-tilt';
import { ShieldCheck, Cpu, ArrowRight, Database, Lock, Layers } from 'lucide-react';
import { TenantId } from '../types';

interface LandingPageProps {
  onSelectCompany: (tenant: 'acme' | 'globex') => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onSelectCompany }) => {
  const [isTouchDevice, setIsTouchDevice] = useState(false);
  const shouldReduceMotion = useReducedMotion();

  useEffect(() => {
    setIsTouchDevice('ontouchstart' in window || navigator.maxTouchPoints > 0);
  }, []);

  return (
    <div className="relative min-h-screen flex flex-col justify-center items-center px-4 py-12 z-10">
      {/* Executive Header */}
      <motion.div
        className="text-center max-w-2xl mx-auto mb-12 sm:mb-16"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/[0.04] border border-white/10 text-slate-300 text-xs font-medium tracking-wide mb-4 backdrop-blur-md shadow-sm">
          <Lock className="w-3.5 h-3.5 text-indigo-400" />
          <span>Multi-Tenant RAG Isolation Platform</span>
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight mb-4">
          Select Corporate Workspace
        </h1>
        <p className="text-sm sm:text-base text-slate-400 leading-relaxed max-w-xl mx-auto">
          Choose an organization to access its cryptographically isolated Chroma collection, corporate policies, and grounded retrieval model.
        </p>
      </motion.div>

      {/* Dual Company Cards (Dark Glassmorphism with Professional Accents) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 max-w-5xl w-full">
        {/* ========================================================= */}
        {/* ACME CORP CARD (Dark Glass with Amber Executive Accent)  */}
        {/* ========================================================= */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="w-full flex justify-center"
        >
          <Tilt
            tiltEnable={!isTouchDevice && !shouldReduceMotion}
            tiltMaxAngleX={8}
            tiltMaxAngleY={8}
            perspective={1200}
            glareEnable={true}
            glareMaxOpacity={0.12}
            glareColor="#F59E0B"
            glarePosition="all"
            scale={1.01}
            transitionSpeed={600}
            className="w-full cursor-pointer rounded-3xl"
          >
            <motion.div
              onClick={() => onSelectCompany('acme')}
              whileHover={{
                scale: 1.015,
                transition: { duration: 0.2 },
              }}
              whileTap={{ scale: 0.99 }}
              className="relative p-8 sm:p-10 rounded-3xl backdrop-blur-2xl bg-white/[0.03] border border-white/10 hover:border-amber-500/40 hover:bg-white/[0.05] shadow-[0_8px_32px_rgba(0,0,0,0.45)] hover:shadow-[0_16px_48px_rgba(245,158,11,0.12)] overflow-hidden transition-all duration-300 group flex flex-col justify-between"
            >
              {/* Subtle amber ambient glow behind card */}
              <div className="absolute top-0 right-0 w-64 h-64 bg-amber-500/[0.07] rounded-full blur-3xl pointer-events-none group-hover:bg-amber-500/[0.14] transition-colors" />

              <div>
                {/* Header Badge & Icon */}
                <div className="flex items-center justify-between mb-6">
                  <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/25 text-amber-400 flex items-center justify-center shadow-inner group-hover:scale-105 transition-transform">
                    <Cpu className="w-7 h-7" />
                  </div>
                  <span className="px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/25 text-amber-300 text-xs font-semibold tracking-wider uppercase">
                    CLUSTER A // AMBER
                  </span>
                </div>

                <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white mb-2 group-hover:text-amber-300 transition-colors">
                  Acme Corporation
                </h2>
                <p className="text-xs font-semibold text-amber-400/90 uppercase tracking-wider mb-4">
                  Engineering, Hardware & High-Yield Prototyping
                </p>
                <p className="text-sm text-slate-300 mb-8 leading-relaxed">
                  Query Acme's internal documentation regarding device testing, prototyping safety protocols, and 90-day evaluation guidelines.
                </p>
              </div>

              {/* Footer Meta & CTA */}
              <div className="pt-6 border-t border-white/10 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Database className="w-3.5 h-3.5 text-amber-400" />
                  <span>34 Handbook Chunks</span>
                </div>
                <span className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-300 text-xs font-semibold tracking-wide group-hover:translate-x-1 transition-all">
                  <span>Enter Workspace</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </span>
              </div>
            </motion.div>
          </Tilt>
        </motion.div>

        {/* ========================================================= */}
        {/* GLOBEX CORP CARD (Dark Glass with Cyan Executive Accent)  */}
        {/* ========================================================= */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="w-full flex justify-center"
        >
          <Tilt
            tiltEnable={!isTouchDevice && !shouldReduceMotion}
            tiltMaxAngleX={8}
            tiltMaxAngleY={8}
            perspective={1200}
            glareEnable={true}
            glareMaxOpacity={0.12}
            glareColor="#06B6D4"
            glarePosition="all"
            scale={1.01}
            transitionSpeed={600}
            className="w-full cursor-pointer rounded-3xl"
          >
            <motion.div
              onClick={() => onSelectCompany('globex')}
              whileHover={{
                scale: 1.015,
                transition: { duration: 0.2 },
              }}
              whileTap={{ scale: 0.99 }}
              className="relative p-8 sm:p-10 rounded-3xl backdrop-blur-2xl bg-white/[0.03] border border-white/10 hover:border-cyan-500/40 hover:bg-white/[0.05] shadow-[0_8px_32px_rgba(0,0,0,0.45)] hover:shadow-[0_16px_48px_rgba(6,182,212,0.12)] overflow-hidden transition-all duration-300 group flex flex-col justify-between"
            >
              {/* Subtle cyan ambient glow behind card */}
              <div className="absolute top-0 right-0 w-64 h-64 bg-cyan-500/[0.07] rounded-full blur-3xl pointer-events-none group-hover:bg-cyan-500/[0.14] transition-colors" />

              <div>
                {/* Header Badge & Icon */}
                <div className="flex items-center justify-between mb-6">
                  <div className="w-14 h-14 rounded-2xl bg-cyan-500/10 border border-cyan-500/25 text-cyan-400 flex items-center justify-center shadow-inner group-hover:scale-105 transition-transform">
                    <ShieldCheck className="w-7 h-7" />
                  </div>
                  <span className="px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/25 text-cyan-300 text-xs font-semibold tracking-wider uppercase">
                    CLUSTER B // CYAN
                  </span>
                </div>

                <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-white mb-2 group-hover:text-cyan-300 transition-colors">
                  Globex Corporation
                </h2>
                <p className="text-xs font-semibold text-cyan-400/90 uppercase tracking-wider mb-4">
                  Enterprise Security, Infrastructure & Intelligence
                </p>
                <p className="text-sm text-slate-300 mb-8 leading-relaxed">
                  Query Globex's restricted knowledge base for enterprise surveillance guidelines, compliance policies, and 180-day probation milestones.
                </p>
              </div>

              {/* Footer Meta & CTA */}
              <div className="pt-6 border-t border-white/10 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Layers className="w-3.5 h-3.5 text-cyan-400" />
                  <span>28 Handbook Chunks</span>
                </div>
                <span className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/30 text-cyan-300 text-xs font-semibold tracking-wide group-hover:translate-x-1 transition-all">
                  <span>Enter Workspace</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </span>
              </div>
            </motion.div>
          </Tilt>
        </motion.div>
      </div>

      {/* Footer System Notice */}
      <motion.p
        className="mt-12 text-xs text-slate-500 text-center max-w-md font-mono"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
      >
        Isolated Chroma Vector Partitions &bull; SQLite Quota Engine &bull; Google OAuth Session Verification
      </motion.p>
    </div>
  );
};
