import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 后端 FastAPI 默认运行在 8765，与 Hermes 等本地服务错开
const BACKEND = process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // ECharts 体积占大头，单独切块避免拖慢首屏
        manualChunks: {
          echarts: ['echarts', 'echarts-for-react'],
          react: ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
});
