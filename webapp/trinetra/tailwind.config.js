/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        saffron: {
          50: '#fff8ed',
          100: '#ffefd1',
          200: '#ffdca3',
          300: '#ffc26a',
          400: '#ff9f2f',
          500: '#ff8008',
          600: '#f06200',
          700: '#c74a02',
          800: '#9e3a0b',
          900: '#7f320e',
        },
      },
      boxShadow: {
        glow: '0 0 40px -8px rgba(255, 128, 8, 0.35)',
      },
      keyframes: {
        pulseRing: {
          '0%': { transform: 'scale(0.9)', opacity: '0.8' },
          '80%, 100%': { transform: 'scale(1.6)', opacity: '0' },
        },
      },
      animation: {
        'pulse-ring': 'pulseRing 1.8s cubic-bezier(0.2, 0.6, 0.4, 1) infinite',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
