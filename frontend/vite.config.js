import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Vite 配置：dev 服务器代理 /api/* 到后端 FastAPI（localhost:8000）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
