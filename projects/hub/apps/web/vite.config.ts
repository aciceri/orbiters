import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  // Served at joinorbiters.com/hub/ by its own nginx (deploy/nginx.conf), so every
  // emitted asset URL carries the prefix. The API client uses absolute `/api/...`
  // paths and does not inherit it.
  base: '/hub/',
  plugins: [react(), tailwindcss()],
  build: {
    rolldownOptions: {
      output: {
        // posthog-js is a third of the bundle and changes only when it is bumped: in a
        // chunk of its own, a release of the hub does not make every browser fetch it
        // again, and the app's own chunk stays under Vite's 500 kB warning.
        codeSplitting: { groups: [{ name: 'posthog', test: /node_modules[\\/]posthog-js/ }] },
      },
    },
  },
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  server: {
    port: 5180,
    // Same origin in dev and in production, so the admin cookie behaves identically.
    proxy: { '/api': { target: 'http://localhost:8084', changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test-setup.ts',
    testTimeout: 20_000,
  },
})
