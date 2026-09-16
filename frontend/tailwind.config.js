/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          bg: '#070A0F',
          surface: '#0E131F',
          card: 'rgba(255, 255, 255, 0.03)',
          border: 'rgba(255, 255, 255, 0.08)',
          text: '#F1F5F9',
          muted: '#94A3B8',
        },
        acme: {
          primary: '#F59E0B',
          'primary-hover': '#D97706',
          accent: '#FBBF24',
          glow: 'rgba(245, 158, 11, 0.25)',
          border: 'rgba(245, 158, 11, 0.35)',
          badge: 'rgba(245, 158, 11, 0.12)',
        },
        globex: {
          primary: '#06B6D4',
          'primary-hover': '#0891B2',
          accent: '#38BDF8',
          glow: 'rgba(6, 182, 212, 0.25)',
          border: 'rgba(6, 182, 212, 0.35)',
          badge: 'rgba(6, 182, 212, 0.12)',
        },
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', '"Inter"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { opacity: 0.4, transform: 'scale(1)' },
          '50%': { opacity: 0.7, transform: 'scale(1.05)' },
        },
        'float-slow': {
          '0%, 100%': { transform: 'translateY(0px) scale(1)' },
          '50%': { transform: 'translateY(-12px) scale(1.02)' },
        },
      },
      animation: {
        'pulse-glow': 'pulse-glow 6s ease-in-out infinite',
        'float-slow': 'float-slow 8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
