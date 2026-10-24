import { resolve } from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

/** The page opens from file://, where module scripts and crossorigin requests are blocked: the app
 * loads as a deferred classic script, after the deferred data.js. */
function classicScript(): Plugin {
  return {
    name: 'classic-script',
    apply: 'build',
    transformIndexHtml: {
      order: 'post',
      handler: (html) => html.replace(/<script type="module" crossorigin/g, '<script defer').replace(/ crossorigin/g, ''),
    },
  };
}

// Vite needs a default export.
export default defineConfig({
  base: './',
  plugins: [react(), tailwindcss(), classicScript()],
  resolve: {
    alias: {
      '@': resolve(import.meta.dirname, './src'),
    },
  },
  build: {
    outDir: '../src/volleyball_stats/site',
    emptyOutDir: true,
    // public/ holds the dev sample data and video.
    copyPublicDir: false,
    modulePreload: false,
    cssCodeSplit: false,
    rolldownOptions: {
      output: { format: 'iife', codeSplitting: false },
    },
  },
});
