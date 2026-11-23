import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { createStatisticsMockMiddleware } from './dev-mocks/statistics.js';

// https://vitejs.dev/config/
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, fileURLToPath(new URL('../', import.meta.url)), '');
  const isMockEnabled = (process.env.MOCK_STATISTICS_API || env.MOCK_STATISTICS_API) === 'true';
  const mockScenario = process.env.MOCK_STATISTICS_SCENARIO || env.MOCK_STATISTICS_SCENARIO || 'normal';

  const mockPlugin = {
    name: 'vite-plugin-statistics-mock',
    configureServer(server) {
      if (command === 'serve' && isMockEnabled) {
        server.middlewares.use(
          createStatisticsMockMiddleware({ scenario: mockScenario, delayMs: 600 })
        );
      }
    },
  };

  return {
    envDir: '../',
    plugins: [react(), mockPlugin],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: process.env.API_PROXY_TARGET || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
