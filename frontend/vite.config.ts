import { defineConfig } from 'vite';
import type { Plugin, ViteDevServer } from 'vite';
import react from '@vitejs/plugin-react';

const backendTarget = 'http://127.0.0.1:8000';

const studioRoutes = ['/projects', '/accounts', '/characters', '/generated-media', '/history', '/voice-lab'];

const studioHistoryFallback = (): Plugin => ({
  name: 'studio-history-fallback',
  configureServer(server: ViteDevServer) {
    server.middlewares.use((req, _res, next) => {
      const accept = String(req.headers.accept || '');
      const method = String(req.method || 'GET').toUpperCase();
      const pathname = new URL(req.url || '/', 'http://localhost:3000').pathname;
      const isStudioRoute = studioRoutes.some((route) => pathname === route || pathname.startsWith(`${route}/`));
      if (method === 'GET' && accept.includes('text/html') && isStudioRoute) {
        req.url = '/';
      }
      next();
    });
  },
});

const backendRoutes = [
  '/auth',
  '/projects',
  '/productions',
  '/social-accounts',
  '/character-presets',
  '/voice-profiles',
  '/voice-lab',
  '/voice-models',
  '/tts',
  '/background-presets',
  '/assets',
  '/generation-jobs',
  '/generated-media',
  '/script-generation',
  '/reviews',
  '/publish-jobs',
  '/publish-history',
  '/routing',
  '/health',
];

export default defineConfig({
  plugins: [studioHistoryFallback(), react()],
  define: {
    'process.env.REACT_APP_API_URL': JSON.stringify(process.env.REACT_APP_API_URL || ''),
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    strictPort: true,
    proxy: Object.fromEntries(
      backendRoutes.map((route) => [
        route,
        {
          target: backendTarget,
          changeOrigin: true,
          secure: false,
        },
      ])
    ),
  },
});
