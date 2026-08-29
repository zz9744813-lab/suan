/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#0a0c10',
          900: '#11141b',
          800: '#181c26',
          700: '#232936',
          600: '#2f3745',
        },
        jade: {
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
        },
        cinnabar: {
          400: '#fb7185',
          500: '#f43f5e',
        },
      },
    },
  },
  plugins: [],
};
