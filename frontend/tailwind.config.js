/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 改用 rgb(var(--xxx) / <alpha-value>) 形式，让所有 utility class
        // (bg-ink-950 / text-slate-300 等) 跟随 [data-theme] 切换。
        // 变量值在 index.css 的 :root / [data-theme='dark'] 分别定义。
        ink: {
          950: 'rgb(var(--ink-950) / <alpha-value>)',
          900: 'rgb(var(--ink-900) / <alpha-value>)',
          850: 'rgb(var(--ink-850) / <alpha-value>)',
          800: 'rgb(var(--ink-800) / <alpha-value>)',
          700: 'rgb(var(--ink-700) / <alpha-value>)',
          600: 'rgb(var(--ink-600) / <alpha-value>)',
        },
        slate: {
          100: 'rgb(var(--slate-100) / <alpha-value>)',
          200: 'rgb(var(--slate-200) / <alpha-value>)',
          300: 'rgb(var(--slate-300) / <alpha-value>)',
          400: 'rgb(var(--slate-400) / <alpha-value>)',
          500: 'rgb(var(--slate-500) / <alpha-value>)',
          600: 'rgb(var(--slate-600) / <alpha-value>)',
          700: 'rgb(var(--slate-700) / <alpha-value>)',
          800: 'rgb(var(--slate-800) / <alpha-value>)',
          900: 'rgb(var(--slate-900) / <alpha-value>)',
          950: 'rgb(var(--slate-950) / <alpha-value>)',
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
        // 卡片浮层：比页面底亮一阶，让卡片从背景中「抬」起来
        surface: 'rgb(var(--surface) / <alpha-value>)',

        // ------ 主题语义色（CSS 变量驱动，日间/夜间随 data-theme 切换）------
        // 页面底 / 卡片底 / 内嵌面板底 / 分隔线 / 通用边框
        page: 'var(--p)',
        card: 'var(--card)',
        panel: 'var(--panel)',
        line: 'var(--line)',
        bd: 'var(--bd)',
        // 文字五档：主 / 次 / 说明 / 弱 / 极弱
        t1: 'var(--t1)',
        t2: 'var(--t2)',
        t3: 'var(--t3)',
        t4: 'var(--t4)',
        t5: 'var(--t5)',
        // 鎏金文字（夜间亮金 / 日间深金）
        gt: 'var(--gt)',
        // 侧边导航 hover / active 底
        navh: 'var(--navh)',
        nava: 'var(--nava)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        lift: 'var(--shadow-lift)',
      },
      transitionTimingFunction: {
        spring: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  plugins: [],
};
