import { describe, expect, it } from 'vitest';
import { windowTitle } from '@/lib/windowTitle';

describe('windowTitle', () => {
  it('names the app in its own window only', () => {
    expect(windowTitle('Statistiques', '127.0.0.1')).toBe('Statistiques – Volleyball Stats');
    expect(windowTitle('Statistiques', 'stats.example.org')).toBe('Statistiques');
  });
});
