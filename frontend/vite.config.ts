/// <reference types="vitest/config" />
import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// base '/static/': FastAPI monta el dist en /static y sirve index.html en /
export default defineConfig({
  base: '/static/',
  plugins: [svelte()],
  resolve: {
    // Para que @testing-library/svelte use el runtime de cliente de Svelte 5
    conditions: ['browser'],
  },
  server: {
    // Desarrollo: el navegador habla con el backend real via proxy
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.ts'],
  },
})