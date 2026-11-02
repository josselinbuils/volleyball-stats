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

  it('accepts the other team losing an attack or a block as the last touch', () => {
    for (const type of ['attack', 'block'] as const) {
      const rally = [c('serve', 1, '1:2'), c('pass', 2, '2:1'), c(type, 2, '2:4', 'point'), c('dig', 1, '1:3', 'error')];
      expect(marks(problems(rally, 2, 1, true))).not.toHaveProperty('3');
    }
    expect(marks(problems([c('serve', 1, '1:2'), c('pass', 2, '2:1'), c('attack', 2, '2:4', 'point'), c('dig', 1, '1:3')], 2, 1, true))[3]).toContain('afterPoint');
  });

  it('marks a touch coming long after the one before', () => {
    const at = (type: string, time: number) => ({ ...c(type, 1), time });
    expect(marks(problems([at('serve', 0), { ...c('pass', 2), time: 1 }, { ...c('set', 2), time: 3.5 }], null, null, false))).toEqual({});
    expect(marks(problems([at('serve', 0), { ...c('pass', 2), time: 1 }, { ...c('set', 2), time: 3.6 }], null, null, false))).toEqual({ 2: ['gap'] });
  });

  it('marks a touch after a point', () => {
    expect(marks(problems([c('serve', 1, '1:2', 'point'), c('pass', 2, '2:1')], 1, null, true))).toEqual({ 1: ['afterPoint'] });
    // A reception lost is the ace's own fault, its last touch.
    expect(marks(problems([c('serve', 1, '1:2', 'point'), c('pass', 2, '2:1', 'error')], 1, null, true))).toEqual({});
  });

  it('marks each problem on the touch that shows it', () => {
    const found = problems([c('pass', 2), c('serve', 1, '', 'error'), c('serve', 1), c('set', 1, '1:4'), c('attack', 1, '1:4')], null, 2, true);
    expect(found.rally).toEqual(['noWinner']);
    expect(marks(found)).toEqual({
      0: ['noServe', 'passWithoutServe'],
      1: ['serveNotReceived', 'server'],
      2: ['twoServes', 'serveNotReceived', 'afterFault'],
      4: ['samePlayer', 'fourTouches'],
    });
  });

  it('takes a playing fault for no touch of the ball, ending the rally', () => {
    const c = (type: string, team: number, result = 'play', player = '') => ({ type, team, result, player });
    // A rotation fault of the receivers at the serve; then a touch after it.
    const found = problems([c('serve', 1), c('fault', 2, 'error'), c('pass', 2)], 1, 1, true);
    expect(found.touch).toEqual(new Map([[2, ['afterFault']]]));
  });
});
