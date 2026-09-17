import React from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { useTheme } from '../context/ThemeContext';

export const BackgroundAmbient: React.FC = () => {
  const { activeTenant } = useTheme();
  const shouldReduceMotion = useReducedMotion();

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0 bg-[#070A0F]">
      {/* Subtle tech grid mesh */}
      <div className="absolute inset-0 tech-grid-bg opacity-30" />

      {/* Atmospheric vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(15,23,42,0.4)_0%,rgba(7,10,15,0.95)_75%)]" />

      {/* Acme Ambient Light Orbs */}
      {activeTenant === 'acme' && (
        <>
          <motion.div
            className="absolute -top-[15%] left-1/4 w-[650px] h-[650px] rounded-full bg-gradient-to-br from-amber-500/15 via-orange-600/10 to-transparent blur-[120px]"
            animate={
              !shouldReduceMotion
                ? {
                    x: [0, 40, -30, 0],
                    y: [0, -30, 20, 0],
                    scale: [1, 1.08, 0.95, 1],
                  }
                : {}
            }
            transition={{ duration: 16, repeat: Infinity, ease: 'easeInOut' }}
          />
          <motion.div
            className="absolute -bottom-[20%] right-1/4 w-[600px] h-[600px] rounded-full bg-gradient-to-tr from-amber-600/10 via-yellow-500/5 to-transparent blur-[140px]"
            animate={
              !shouldReduceMotion
                ? {
                    x: [0, -35, 25, 0],
                    y: [0, 25, -20, 0],
                  }
                : {}
            }
            transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut', delay: 2 }}
          />
        </>
      )}

      {/* Globex Ambient Light Orbs */}
      {activeTenant === 'globex' && (
        <>
          <motion.div
            className="absolute -top-[15%] right-1/4 w-[650px] h-[650px] rounded-full bg-gradient-to-br from-cyan-500/15 via-blue-600/10 to-transparent blur-[120px]"
            animate={
              !shouldReduceMotion
                ? {
                    x: [0, -40, 30, 0],
                    y: [0, 30, -20, 0],
                    scale: [1, 1.08, 0.95, 1],
                  }
                : {}
            }
            transition={{ duration: 16, repeat: Infinity, ease: 'easeInOut' }}
          />
          <motion.div
            className="absolute -bottom-[20%] left-1/4 w-[600px] h-[600px] rounded-full bg-gradient-to-tr from-blue-600/10 via-indigo-500/5 to-transparent blur-[140px]"
            animate={
              !shouldReduceMotion
                ? {
                    x: [0, 35, -25, 0],
                    y: [0, -25, 20, 0],
                  }
                : {}
            }
            transition={{ duration: 18, repeat: Infinity, ease: 'easeInOut', delay: 2 }}
          />
        </>
      )}

      {/* Neutral Selection Ambient Orbs */}
      {!activeTenant && (
        <>
          {/* Left Amber Glow for Acme card */}
          <div className="absolute top-1/3 -left-20 w-[500px] h-[500px] rounded-full bg-amber-500/10 blur-[130px]" />
          {/* Right Cyan Glow for Globex card */}
          <div className="absolute top-1/3 -right-20 w-[500px] h-[500px] rounded-full bg-cyan-500/10 blur-[130px]" />
          {/* Central subtle violet ambient light */}
          <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[700px] h-[400px] rounded-full bg-indigo-500/10 blur-[120px]" />
        </>
      )}
    </div>
  );
};
