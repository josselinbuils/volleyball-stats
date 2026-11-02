import { describe, expect, it, vi } from 'vitest';

describe('lineStarting', () => {
  async function load() {
    vi.stubGlobal('window', { MATCH: { rallies: [], contacts: [], people: {} } });
    return import('@/lib/voice');
  }

  const lines: [number, string, number][] = [
    [10, 'a.mp3', 1],
    [12, 'b.mp3', 2],
  ];

  it('finds a line only just as it starts, so a jump into the middle of one stays silent', async () => {
    const { lineStarting } = await load();
    expect(lineStarting(lines, 9.9, 0.5)).toBeUndefined();
    expect(lineStarting(lines, 10.1, 0.5)?.[1]).toBe('a.mp3');
    expect(lineStarting(lines, 10.6, 0.5)).toBeUndefined();
    expect(lineStarting(lines, 12, 0.5)?.[1]).toBe('b.mp3');
  });
});
