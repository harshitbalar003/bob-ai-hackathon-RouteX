/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          base: '#0e1621',
          raised: '#162032',
          border: '#263350',
          map: '#0a1118',
        },
        text: {
          primary: '#e8edf5',
          muted: '#7e94b4',
        },
        accent: {
          disruption: '#e8a03a',
          tracking: '#3ab8c8',
          critical: '#e84040',
          minor: '#5b9cf6',
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', '"Courier New"', 'monospace'],
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1.4' }],
        sm: ['0.8125rem', { lineHeight: '1.5' }],
        base: ['0.9375rem', { lineHeight: '1.6' }],
        lg: ['1.0625rem', { lineHeight: '1.5' }],
        xl: ['1.25rem', { lineHeight: '1.4' }],
        '2xl': ['1.5rem', { lineHeight: '1.3' }],
      },
      fontVariantNumeric: {
        tabular: 'tabular-nums',
      },
    },
  },
  safelist: [
    'border-l-accent-critical',
    'border-l-accent-disruption',
    'border-l-surface-border',
  ],
  plugins: [],
};
