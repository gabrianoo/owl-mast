/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs';
import { defineConfig, type Plugin } from 'vite';
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

// The build publishes the API contract it supports next to the shell (`/api-compatibility.json`), so
// the pre-rollout check can read it from the deployed artifact instead of a checkout that may be at
// another commit (scripts/check-api-compatibility.py --frontend-url). The bundle still inlines it.
const publishApiCompatibility: Plugin = {
  name: 'owlmast-publish-api-compatibility',
  apply: 'build',
  generateBundle() {
    this.emitFile({
      type: 'asset',
      fileName: 'api-compatibility.json',
      source: readFileSync(new URL('./api-compatibility.json', import.meta.url), 'utf8'),
    });
  },
};

export default defineConfig({
  plugins: [react(), publishApiCompatibility],
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
