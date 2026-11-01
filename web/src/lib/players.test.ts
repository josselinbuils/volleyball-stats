import { describe, expect, it, vi } from 'vitest';

describe('unpackChunk', () => {
  it('gives back the positions, across chunks and with a person away', async () => {
    vi.stubGlobal('window', { MATCH: { rallies: [], contacts: [], people: {} } });
    const { unpackChunk } = await import('@/lib/players');
    const samples: number[][] = [];
    const last = { x: [], y: [] };
    unpackChunk('[[[1,2],[1],[]],[[-580,153],[1],[]],[[332,-7],[-1],[]]]', last, samples);
    unpackChunk('[[[2,1]],[[-3,2]],[[5,0]]]', last, samples);
    expect(samples).toEqual([[1, -5.8, 3.32, 2, 1.53, -0.07], [1, -5.79, 3.31], [], [2, 1.5, -0.02, 1, -5.77, 3.31]]);
    vi.unstubAllGlobals();
  });
});
