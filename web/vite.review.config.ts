import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/** The review's screens, a classic script of their own, loaded by the page only when the review server serves it:
 * the page viewers open stays as light as without them. */
// Vite needs a default export.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(import.meta.dirname, './src'),
    },
  },
  // A library build leaves it to its host otherwise, and React reads it.
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: '../src/volleyball_stats/site',
    emptyOutDir: false,
    copyPublicDir: false,
    lib: {
      entry: resolve(import.meta.dirname, 'src/reviewApp.tsx'),
      name: 'VolleyReviewBundle',
      formats: ['iife'],
      fileName: () => 'review-app.js',
    },
  },
});
