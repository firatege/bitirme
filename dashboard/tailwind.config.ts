import type { Config } from 'tailwindcss';

/**
 * Operasyonel kontrol paneli paleti.
 * Brand: antique / regal gold (sınıf, otorite, otorite hissi).
 * Surface: bold black + cool grey-line.
 * Navy: ikinci aksent (status, chart vurguları).
 */
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Marka — antique gold
        brand: {
          50: '#fbf6e8',
          100: '#f4ead0',
          200: '#ead49b',
          300: '#dcb963',
          400: '#cda142',
          500: '#b8862b',
          600: '#9a6e1f',
          700: '#7a571a',
          800: '#5d4115',
          900: '#3d2b0e',
          950: '#231906',
        },
        // İkinci aksent — deep navy
        navy: {
          400: '#3b5378',
          500: '#27406a',
          600: '#1b3158',
          700: '#142647',
          800: '#0c1a2e',
          900: '#08152b',
          950: '#040b1a',
        },
        // Yüzeyler — bold black
        surface: {
          0: '#08090c',
          1: '#0e1118',
          2: '#161a23',
          3: '#1f2530',
          line: '#2a3140',
          mute: '#3a4254',
        },
        // Aciliyet — fonksiyonel + uyumlu
        urgency: {
          critical: '#dc2626',
          high: '#ea580c',
          medium: '#ca8a04',
          low: '#0d9488',
          unknown: '#64748b',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Consolas',
          'monospace',
        ],
      },
      boxShadow: {
        card: '0 1px 0 rgba(255,255,255,0.02) inset',
      },
      keyframes: {
        'slide-in': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'slide-in': 'slide-in 0.15s ease-out',
      },
    },
  },
  plugins: [],
};

export default config;
