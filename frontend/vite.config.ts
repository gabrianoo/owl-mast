/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Development and preview servers proxy the backend paths from the routing contract
// (deploy/helm/owl-mast/values.yaml `routing.*`). The production image never proxies; the
// ingress/gateway routes `/api` and `/actuator` to the backend service instead.
//
// Keys are anchored path-segment regexes, like the ingress `Prefix` match: a plain '/api' key is a
// string prefix and would also forward the frontend's own `/api-compatibility.json` module.
const backendUrl = process.env.OWLMAST_BACKEND_URL ?? 'http://127.0.0.1:8080';
const proxy = {
  '^/api(?:[/?]|$)': { target: backendUrl, changeOrigin: false },
  '^/actuator(?:[/?]|$)': { target: backendUrl, changeOrigin: false },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 4173, strictPort: true, proxy },
  build: {
    target: 'es2022',
    sourcemap: false,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/main.tsx'],
    },
  },
});
