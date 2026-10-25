import { resolve } from 'node:path';
import { defineConfig } from 'vite';

/** The 3D view, a classic script of its own (three.js), loaded by the page when it is first shown:
 * the page itself stays as light as without it. */
// Vite needs a default export.
export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(import.meta.dirname, './src'),
    },
  },
  build: {
    outDir: '../src/volleyball_stats/site',
    emptyOutDir: false,
    copyPublicDir: false,
    lib: {
      entry: resolve(import.meta.dirname, 'src/scene3d/index.ts'),
      name: 'VolleySceneBundle',
      formats: ['iife'],
      fileName: () => 'scene3d.js',
    },
  },
});
