import { describe, expect, it } from 'vitest';
import { onAppServer, reviewPreview, windowTitle } from '@/lib/appServer';

describe('appServer', () => {
  it('names the app in its own window only', () => {
    expect(windowTitle('Statistiques', '127.0.0.1')).toBe('Statistiques – Volleyball Stats');
    expect(windowTitle('Statistiques', 'stats.example.org')).toBe('Statistiques');
  });

  it('knows the app’s server from the hosted pages', () => {
    expect(onAppServer('localhost')).toBe(true);
    expect(onAppServer('stats.example.org')).toBe(false);
  });

  it('knows the review’s page by its path, whatever the address', () => {
    expect(reviewPreview('/page')).toBe(true);
    expect(reviewPreview('/2026-11-12-aspom-1-vs-le-haillan-1/')).toBe(false);
  });
});
