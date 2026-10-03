import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    restoreMocks: true,
    unstubGlobals: true,
    clearMocks: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': process.env.CONTROLPLANE_URL || 'http://127.0.0.1:8082',
      '/gateway/check': process.env.CONTROLPLANE_URL || 'http://127.0.0.1:8082',
    },
  },
});
