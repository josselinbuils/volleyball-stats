import { describe, expect, it } from 'vitest';
import { problems, type Checked } from '@/components/Review/helpers/checks';

describe('problems', () => {
  const c = (type: string, team: number, player = '', result = 'play'): Checked => ({ type, team, player, result });
  const marks = (found: ReturnType<typeof problems>) => Object.fromEntries(found.touch);

  it('finds nothing in a clean rally', () => {
    const found = problems([c('serve', 1, '1:2'), c('pass', 2, '2:1'), c('set', 2, '2:3'), c('attack', 2, '2:4', 'point')], 2, 1, true);
    expect(found.rally).toEqual([]);
    expect(marks(found)).toEqual({});
  });

  it('marks a touch after a point', () => {
    expect(marks(problems([c('serve', 1, '1:2', 'point'), c('pass', 2, '2:1')], 1, null, true))).toEqual({ 1: ['afterPoint'] });
    // A touched ace is no point: the reception's fault wins the rally.
    expect(marks(problems([c('serve', 1, '1:2', 'point'), c('pass', 2, '2:1', 'error')], 1, null, true))).toEqual({ 1: ['afterPoint'] });
  });

  it('marks each problem on the touch that shows it', () => {
    const found = problems([c('pass', 2), c('serve', 1, '', 'error'), c('serve', 1), c('set', 1, '1:4'), c('attack', 1, '1:4')], null, 2, true);
    expect(found.rally).toEqual(['noWinner']);
    expect(marks(found)).toEqual({
      0: ['noServe', 'passWithoutServe'],
      1: ['serveNotReceived', 'server'],
      2: ['twoServes', 'afterFault', 'serveNotReceived'],
      4: ['samePlayer', 'fourTouches'],
    });
  });
});
