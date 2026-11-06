import { describe, expect, it } from 'vitest';
import { seekLine } from '@/components/Watch/helpers/seekBar';

describe('seekLine', () => {
  const colors = { played: 'P', heldColor: 'H', rest: 'R' };

  it('draws the played part, then the loaded stretches inside the bar, over the rest', () => {
    // The bar spans 100 s to 200 s; loaded: 50-120 s (cut at the bar's start), 150-160 s, 300-310 s (past its end).
    const line = seekLine(
      125,
      100,
      200,
      [
        [50, 120],
        [150, 160],
        [300, 310],
      ],
      colors,
    );
    expect(line.backgroundImage).toBe(
      'linear-gradient(P, P), linear-gradient(to right, transparent 0%, H 0% 20%, transparent 20%, transparent 50%, H 50% 60%, transparent 60%), linear-gradient(R, R)',
    );
    expect(line.backgroundSize).toBe('25% 4px, 100% 4px, 100% 4px');
  });

  it('has no loaded layer before anything loads', () => {
    expect(seekLine(0, 0, 10, [], colors).backgroundImage).toBe('linear-gradient(P, P), linear-gradient(R, R)');
  });
});
