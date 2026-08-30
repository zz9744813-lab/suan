/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#08090d',
          900: '#0e1118',
          850: '#131722',
          800: '#1a1f2c',
          700: '#252c3b',
          600: '#333c4f',
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
        gilt: {
          300: '#ecd9a0',
          400: '#d9b96a',
          500: '#c9a227',
          600: '#a8861d',
        },
        // 卡片浮层：比页面底(#08090d)亮一阶，让卡片从背景中「抬」起来
        surface: '#11151f',
      },
      boxShadow: {
        card: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)',
        lift: '0 1px 0 0 rgba(255,255,255,0.05) inset, 0 16px 40px -16px rgba(0,0,0,0.75)',
      },
      transitionTimingFunction: {
        spring: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
};
