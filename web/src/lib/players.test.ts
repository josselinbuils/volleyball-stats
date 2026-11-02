import { describe, expect, it, vi } from 'vitest';

describe('players', () => {
  async function load() {
    vi.stubGlobal('window', { MATCH: { rallies: [], contacts: [], people: {} } });
    const found = await import('@/lib/players');
    vi.unstubAllGlobals();
    return found;
  }

  describe('unpackFile', () => {
    it('gives back the positions, in their place, with a person away', async () => {
      const { unpackFile } = await load();
      const samples: number[][] = [];
      unpackFile(
        samples,
        3,
        1,
        [
          3,
          [
            [1, [0, 2], [-116, 0], [66, -1]],
            [2, [0, 1], [31], [-1]],
          ],
        ],
        5,
      );
      expect(samples.slice(3)).toEqual([[1, -5.8, 3.3, 2, 1.55, -0.05], [1, -5.8, 3.25], []]);
      expect(samples[0]).toBeUndefined();
    });
  });

  describe('filesAt', () => {
    it('takes the file of the moment, and the next near its end', async () => {
      const { filesAt } = await load();
      expect(filesAt(0, 60, 3)).toEqual([0]);
      expect(filesAt(49.9, 60, 3)).toEqual([0]);
      expect(filesAt(50, 60, 3)).toEqual([0, 1]);
      expect(filesAt(60, 60, 3)).toEqual([1]);
    });

    it('stays within the files', async () => {
      const { filesAt } = await load();
      expect(filesAt(179, 60, 3)).toEqual([2]);
      expect(filesAt(200, 60, 3)).toEqual([]);
    });
  });
});
