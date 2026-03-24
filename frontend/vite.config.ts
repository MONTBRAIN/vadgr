/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const FRONTEND_PORT = Number(process.env.AGENT_FORGE_FRONTEND_PORT) || 3000
const API_PORT = Number(process.env.AGENT_FORGE_PORT) || 8000
const API_TARGET = `http://127.0.0.1:${API_PORT}`

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: FRONTEND_PORT,
    proxy: {
      '/api/ws': {
        target: API_TARGET,
        ws: true,
      },
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
    css: true,
  },
})
