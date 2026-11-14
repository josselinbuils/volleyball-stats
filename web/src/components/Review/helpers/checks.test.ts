import { describe, expect, it } from 'vitest';
import { problems, warningTimes, type Checked, type Problem } from '@/components/Review/helpers/checks';

describe('warningTimes', () => {
  const touches = [{ time: 10 }, { time: 12 }, { time: 15 }];
  const gap: Problem[] = ['gap'];

  it('flags each touch with a problem', () => {
    const touch = new Map<number, Problem[]>([
      [1, gap],
      [2, ['afterPoint']],
    ]);
    expect(warningTimes({ rally: [], touch }, touches, 9, 20, false)).toEqual([12, 15]);
  });

  it('flags the start for no touch, the end for no winner or a set off its score', () => {
    expect(warningTimes({ rally: ['empty'], touch: new Map() }, [], 9, 20, false)).toEqual([9]);
    expect(warningTimes({ rally: ['noWinner'], touch: new Map<number, Problem[]>([[0, ['noServe']]]) }, touches, 9, 20, false)).toEqual([10, 20]);
    expect(warningTimes(undefined, touches, 9, 20, true)).toEqual([20]);
  });

  it('flags nothing in a clean rally', () => {
    expect(warningTimes({ rally: [], touch: new Map() }, touches, 9, 20, false)).toEqual([]);
  });
});

describe('problems', () => {
  const c = (type: string, team: number, player = '', result = 'play'): Checked => ({ type, team, player, result });
  const marks = (found: ReturnType<typeof problems>) => Object.fromEntries(found.touch);

  it('finds nothing in a clean rally', () => {
    const found = problems([c('serve', 1, '1:2'), c('pass', 2, '2:1'), c('set', 2, '2:3'), c('attack', 2, '2:4', 'point')], 2, 1, true);
    expect(found.rally).toEqual([]);
    expect(marks(found)).toEqual({});
  });

  it('marks a relance as first touch, even in a checked rally', () => {
    expect(marks(problems([c('serve', 1), c('pass', 2), c('relance', 1)], 1, null, true, true))[2]).toEqual(['relanceFirst']);
    expect(marks(problems([c('attack', 1), c('block', 2), c('relance', 2)], 1, null, true, true))[2]).toEqual(['relanceFirst']);
    expect(marks(problems([c('serve', 1), c('pass', 2), c('set', 2), c('relance', 2)], 2, null, true, true))).toEqual({});
  });

  it('marks a relance as second touch, even in a checked rally', () => {
    expect(marks(problems([c('serve', 1), c('pass', 2), c('relance', 2)], 1, null, true, true))[2]).toEqual(['relanceSecond']);
    expect(marks(problems([c('attack', 1), c('block', 2), c('dig', 2), c('relance', 2)], 1, null, true, true))[3]).toEqual(['relanceSecond']);
  });

  it('marks a fault after a point: the labels say what happened, the statistics read the point', () => {
    for (const type of ['attack', 'block'] as const) {
      const rally = [c('serve', 1, '1:2'), c('pass', 2, '2:1'), c(type, 2, '2:4', 'point'), c('dig', 1, '1:3', 'error')];
      expect(marks(problems(rally, 2, 1, true))[3]).toEqual(['afterPoint']);
    }
  });

  it('marks a touch coming long after the one before', () => {
    const at = (type: string, time: number) => ({ ...c(type, 1), time });
    expect(marks(problems([at('serve', 0), { ...c('pass', 2), time: 1 }, { ...c('set', 2), time: 3.5 }], null, null, false))).toEqual({});
    expect(marks(problems([at('serve', 0), { ...c('pass', 2), time: 1 }, { ...c('set', 2), time: 3.6 }], null, null, false))).toEqual({ 2: ['gap'] });
  });

  it('marks a touch after a point', () => {
    expect(marks(problems([c('serve', 1, '1:2', 'point'), c('pass', 2, '2:1')], 1, null, true))).toEqual({ 1: ['afterPoint'] });
    expect(marks(problems([c('serve', 1, '1:2', 'point'), c('pass', 2, '2:1', 'error')], 1, null, true))).toEqual({ 1: ['afterPoint'] });
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

  describe('what may be right after all', () => {
    const at = (type: string, team: number, time: number, result = 'play') => ({ ...c(type, team, '', result), time });
    const others = ['noServe', 'passWithoutServe', 'serveNotReceived', 'afterPoint', 'afterFault', 'noWinner'];
    // The touches after a first one, without the problems a rally not starting with a serve has anyway.
    const of = (rally: Checked[], teams = false, validated = false) =>
      Object.fromEntries(
        [...problems(rally, 1, null, teams, validated).touch].flatMap(([k, list]) => {
          const mine = list.filter((p) => !others.includes(p));
          return mine.length ? [[k, mine]] : [];
        }),
      );

    it('marks a touch seen twice, not a block on its attack', () => {
      expect(of([at('dig', 2, 1), at('set', 2, 1.25)])[1]).toEqual(['doubleTouch']);
      expect(of([at('dig', 2, 1), at('set', 2, 1.4)])).toEqual({});
      expect(of([at('dig', 2, 1), at('dig', 1, 1.25)])[1]).toEqual(['doubleTouch']);
      expect(of([at('attack', 1, 0), at('block', 2, 0.1)])).toEqual({});
    });

    it("marks touches out of a team's order", () => {
      expect(of([c('attack', 1), c('dig', 1)])[1]).toEqual(['overThenSameTeam', 'digLater']);
      expect(of([c('relance', 1), c('set', 1)])[1]).toEqual(['overThenSameTeam']);
      expect(of([c('set', 1), c('dig', 2)])[0]).toEqual(['setToOtherTeam']);
      expect(of([c('attack', 1), c('set', 2)])[1]).toEqual(['setFirst']);
      expect(of([c('set', 1), c('set', 1)])[1]).toEqual(['twoSets']);
      expect(of([c('attack', 1), c('block', 2), c('dig', 1)])).toEqual({});
    });

    it('marks a rally ending oddly, not one to replay nor one a playing fault ends', () => {
      const pass = c('pass', 2);
      expect(of([c('serve', 1), pass, c('set', 2)], true)[2]).toEqual(['endsOnSet']);
      expect(of([c('serve', 1), pass, c('dig', 2, '', 'point')], true)[2]).toEqual(['digLater', 'pointOnTouch']);
      expect(of([c('serve', 1), pass, c('set', 2), c('relance', 2, '', 'point')], true)).toEqual({});
      expect(of([c('serve', 1, '', 'point')], true)[0]).toEqual(['ace']);
      expect(of([c('serve', 1), pass, c('set', 2)])).toEqual({});
      expect(of([c('serve', 1), pass, c('set', 2), c('fault', 1, '', 'error')], true)).toEqual({});
    });

    it('shows none of it on a rally checked', () => {
      expect(of([at('set', 1, 0), at('dig', 2, 1), at('set', 2, 1.1)], true, true)).toEqual({});
    });
  });

  it('takes a playing fault for no touch of the ball, ending the rally', () => {
    const c = (type: string, team: number, result = 'play', player = '') => ({ type, team, result, player });
    // A rotation fault of the receivers at the serve; then a touch after it.
    const found = problems([c('serve', 1), c('fault', 2, 'error'), c('pass', 2)], 1, 1, true);
    expect(found.touch).toEqual(new Map([[2, ['afterFault']]]));
  });
});
