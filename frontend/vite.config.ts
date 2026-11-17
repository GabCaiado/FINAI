/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Where the dev server forwards /api/*. It comes from frontend/.env (API_PROXY_TARGET), never
  // from code. In production Vercel does the same job through the rewrite in vercel.json.
  const env = loadEnv(mode, process.cwd(), '')
  const apiProxyTarget = env.API_PROXY_TARGET

  return {
    plugins: [react(), tailwindcss()],
    server: {
      proxy: apiProxyTarget ? { '/api': apiProxyTarget } : undefined,
    },
    test: {
      environment: 'jsdom',
      globals: true,
    },
  }
})
