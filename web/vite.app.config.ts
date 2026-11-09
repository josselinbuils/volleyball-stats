import { resolve } from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/** The app's screens on the review server's list of the matches (importing, the court, the analysis, the machine's
 * checks), a classic script of their own: the hosted list never loads them. */
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
    outDir: '../src/volleyball_stats/matches_site',
    emptyOutDir: false,
    copyPublicDir: false,
    lib: {
      entry: resolve(import.meta.dirname, 'src/appPanel.tsx'),
      name: 'VolleyAppBundle',
      formats: ['iife'],
      fileName: () => 'app.js',
    },
  },
});
