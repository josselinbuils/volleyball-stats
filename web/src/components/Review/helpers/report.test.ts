import { describe, expect, it } from 'vitest';
import type { Group } from '@/lib/match';
import {
  settled,
  closedEnd,
  aboutEnd,
  changedSince,
  comingFirstTouch,
  freeFrame,
  joinEnd,
  joinStart,
  liveReports,
  unwarnedReports,
  matchFinished,
  nextServer,
  nextTouch,
  offGiven,
  openingTime,
  pieceOf,
  rallyAt,
  rallyOf,
  restored,
  runningScores,
  sliceOf,
  splitAfter,
  timeoutsAfter,
  withAdded,
  withSplits,
} from '@/components/Review/helpers/report';

describe('comingFirstTouch', () => {
  const rallies = [{ end: 10 }, { end: 30 }];
  const touches = [
    { time: 5, rally: 0 },
    { time: 8, rally: 0 },
    { time: 25, rally: 1 },
    { time: 27, rally: 1 },
  ];

  it('names the first rally from the start of the match', () => {
    expect(comingFirstTouch(touches, rallies, 0, 0.2)).toBe(touches[0]);
  });

  it('waits for the rally before to be over', () => {
    expect(comingFirstTouch(touches, rallies, 10.9, 0.2)).toBeUndefined();
    expect(comingFirstTouch(touches, rallies, 11, 0.2)).toBe(touches[2]);
    expect(comingFirstTouch(touches, rallies, 24, 0.2)).toBe(touches[2]);
  });

  it('leaves the rest of a rally alone', () => {
    expect(comingFirstTouch(touches, rallies, 6, 0.2)).toBeUndefined();
    expect(comingFirstTouch(touches, rallies, 26, 0.2)).toBeUndefined();
    expect(comingFirstTouch(touches, rallies, 28, 0.2)).toBeUndefined();
  });
});

describe('openingTime', () => {
  const rallies = [{ key: 100, start: 10 }, { start: 20 }, { key: 300, start: 30 }];
  const reports = [{ reports: [{ time: 25 }] }];

  it('opens before the first rally not checked, whatever the reports', () => {
    expect(openingTime(rallies, [100], [{ reports: [{ time: 30 }] }], 50)).toBe(18);
  });

  it('takes the key of a rally without one from its start', () => {
    expect(openingTime(rallies, [100, 1000], reports, 50)).toBe(28);
  });

  it('opens on the first report once all are checked', () => {
    expect(openingTime(rallies, [100, 1000, 300], reports, 50)).toBe(23);
  });

  it('opens on the first rally with all checked and no report', () => {
    expect(openingTime(rallies, [100, 1000, 300], [], 50)).toBe(8);
  });

  it('never opens before the video', () => {
    expect(openingTime([{ start: 1 }], [], [], 50)).toBe(0);
    expect(openingTime([], [], [], 50)).toBe(0);
  });
});

describe('sliceOf and restored', () => {
  // Rally 100 covers frames 90 to 190; the one after it, 190 on.
  const saved = {
    touches: [
      { frame: 50, player: '1:2' },
      { frame: 120, player: '1:4' },
      { frame: 200, type: 'set' },
    ],
    added: [{ frame: 150, team: 1 as const, type: 'set', result: 'play' }],
    rallies: [
      { start: 80, winner: 2 as const },
      { start: 100, winner: 1 as const },
    ],
    splits: [100],
  };

  it("keeps the rally's corrections, its own start out", () => {
    expect(sliceOf(saved, 100, 90, 190)).toEqual({
      from: 90,
      to: 190,
      touches: [{ frame: 120, player: '1:4' }],
      added: [{ frame: 150, team: 1, type: 'set', result: 'play' }],
      rallies: [{ start: 100, winner: 1 }],
    });
  });

  it('puts the rally back as it was and leaves the others as they stand', () => {
    const now = {
      touches: [
        { frame: 50, player: '1:3' },
        { frame: 130, player: 'none' },
        { frame: 200, type: 'set' },
      ],
      rallies: [
        { start: 80, winner: 2 as const },
        { start: 100, winner: 2 as const },
      ],
      splits: [100, 140],
    };

    expect(restored(now, 100, sliceOf(saved, 100, 90, 190))).toEqual({
      touches: [
        { frame: 50, player: '1:3' },
        { frame: 120, player: '1:4' },
        { frame: 200, type: 'set' },
      ],
      added: [{ frame: 150, team: 1, type: 'set', result: 'play' }],
      rallies: [
        { start: 80, winner: 2 },
        { start: 100, winner: 1 },
      ],
      splits: [100],
    });
  });
});

describe('changedSince', () => {
  const saved = {
    touches: [{ frame: 10, player: '1:4', type: 'pass' }],
    added: [{ frame: 20, team: 1 as const, type: 'set', result: 'play' }],
    rallies: [{ start: 100, winner: 1 as const }],
    splits: [200],
  };

  it('finds nothing when the corrections are those saved, whatever their fields order', () => {
    expect(changedSince({ ...saved, touches: [{ type: 'pass', frame: 10, player: '1:4' }] }, saved)).toEqual({ frames: [], starts: [] });
  });

  it('finds nothing with no correction at all', () => {
    expect(changedSince({ touches: [] }, {})).toEqual({ frames: [], starts: [] });
  });

  it('finds a touch changed, added or taken back', () => {
    expect(changedSince({ ...saved, touches: [{ frame: 10, player: '1:5', type: 'pass' }] }, saved).frames).toEqual([10]);
    expect(changedSince({ ...saved, touches: [...saved.touches, { frame: 30, type: 'set' }] }, saved).frames).toEqual([30]);
    expect(changedSince({ ...saved, touches: [] }, saved).frames).toEqual([10]);
    expect(changedSince({ touches: saved.touches, rallies: saved.rallies, splits: saved.splits }, saved).frames).toEqual([20]);
  });

  it('finds a rally changed or started, its fix or its start taken back', () => {
    expect(changedSince({ ...saved, rallies: [{ start: 100, winner: 2 }] }, saved).starts).toEqual([100]);
    expect(changedSince({ ...saved, rallies: undefined }, saved).starts).toEqual([100]);
    expect(changedSince({ ...saved, splits: [200, 300] }, saved).starts).toEqual([300]);
    expect(changedSince({ ...saved, splits: [] }, saved).starts).toEqual([200]);
  });
});

describe('timeoutsAfter', () => {
  const rallies = [{ start: 10 }, { start: 30 }];
  const timeouts = [{ start: 50 }, { start: 250 }, { start: 500 }];

  it('lists each timeout after the last rally started before it', () => {
    expect(timeoutsAfter(rallies, timeouts, -1, 10)).toEqual([{ start: 50 }]);
    expect(timeoutsAfter(rallies, timeouts, 0, 10)).toEqual([{ start: 250 }]);
    expect(timeoutsAfter(rallies, timeouts, 1, 10)).toEqual([{ start: 500 }]);
  });
});

describe('rallyAt', () => {
  const rallies = [
    { start: 10, end: 20 },
    { start: 30, end: 40 },
  ];

  it('takes the rally the moment falls in, from a little before its start', () => {
    expect(rallyAt(rallies, 15)).toBe(0);
    expect(rallyAt(rallies, 29.8)).toBe(1);
  });

  it('takes the rally just ended between two, the first before any', () => {
    expect(rallyAt(rallies, 25)).toBe(0);
    expect(rallyAt(rallies, 50)).toBe(1);
    expect(rallyAt(rallies, 2)).toBe(0);
  });
});

describe('rallyOf', () => {
  const rallies = [
    { start: 10, end: 20 },
    { start: 40, end: 50 },
  ];

  it('files a serve outside the rallies under the next one, another touch under the one before', () => {
    expect(rallyOf(rallies, 35, 'serve')).toBe(1);
    expect(rallyOf(rallies, 5, 'serve')).toBe(0);
    expect(rallyOf(rallies, 35, 'dig')).toBe(0);
    expect(rallyOf(rallies, 15, 'serve')).toBe(0);
    expect(rallyOf(rallies, 60, 'serve')).toBe(1);
  });
});

describe('withAdded', () => {
  it('starts a rally at a serve added before it, so the touches added after it are its own', () => {
    const rallies = withAdded(
      [
        { start: 10, end: 20 },
        { start: 40, end: 50 },
      ],
      [
        { time: 35, type: 'serve' },
        { time: 36, type: 'pass' },
      ],
    );
    expect(rallies.map((r) => r.start)).toEqual([10, 35]);
    expect(rallies.map((r) => r.end)).toEqual([20, 50]);
    expect(rallyOf(rallies, 36, 'pass')).toBe(1);
  });
});

describe('aboutEnd', () => {
  it('holds only when every report is about how the rally ended', () => {
    expect(aboutEnd({ reports: [{ kind: 'auto.boardOff' }, { kind: 'auto.missedPoint' }] })).toBe(true);
    expect(aboutEnd({ reports: [{ kind: 'auto.boardOff' }, { kind: 'auto.gap' }] })).toBe(false);
    expect(aboutEnd({ reports: [] })).toBe(false);
  });
});

describe('freeFrame', () => {
  it('keeps a frame next to a touch, and moves on from one holding a touch', () => {
    expect(freeFrame([100], 101)).toBe(101);
    expect(freeFrame([100, 101], 100)).toBe(102);
  });
});

describe('splitAfter', () => {
  it('starts the new rally at the first touch after the end, where that touch falls in it', () => {
    expect(splitAfter([12.3, 18.1, 15.04], 14, 25)).toBe(376);
    expect(withSplits([{ start: 10, end: 20, set: 1, winner: 1, key: 250 }], [splitAfter([12.3, 15.04], 14, 25)!], 25)[1].start).toBeLessThanOrEqual(15.04);
    expect(splitAfter([12.3], 14, 25)).toBeUndefined();
    expect(splitAfter([], 14, 25)).toBeUndefined();
  });
});

describe('withSplits', () => {
  const rallies = [
    { start: 10, end: 20, set: 1, winner: 1 as const, key: 100 },
    { start: 50, end: 60, set: 2, winner: 2 as const, key: 500 },
  ];

  it('starts a rally inside one or between two as the server does, the others keeping their key', () => {
    const out = withSplits(
      rallies,
      [15, 30, 50, 5].map((s) => s * 10),
      10,
    );

    expect(out.map((r) => [r.start, r.end, r.set, r.winner, r.key, r.origin, r.added])).toEqual([
      [5, 5, 1, null, 50, null, true],
      [10, 14.9, 1, null, 100, 0, false],
      [15, 20, 1, 1, 150, 0, true],
      [30, 30, 1, null, 300, null, true],
      [50, 60, 2, 2, 500, 1, false],
    ]);
  });

  it('leaves "to replay" and the referee\'s error on the part of a rally keeping its key', () => {
    const out = withSplits([{ start: 10, end: 20, set: 1, winner: null, redo: true, wrongCall: true, key: 100 }], [150], 10);

    expect(out.map((r) => [r.key, r.redo, r.wrongCall])).toEqual([
      [100, true, true],
      [150, undefined, undefined],
    ]);
  });

  it('files a page touch under the part of its rally started by then', () => {
    const out = withSplits(rallies, [150], 10);

    expect([pieceOf(out, 0, 12), pieceOf(out, 0, 16), pieceOf(out, 0, 9.8), pieceOf(out, 1, 55)]).toEqual([0, 1, 0, 2]);
  });
});

describe('nextTouch', () => {
  it('follows the touch before as a rally goes, a serve by the server first', () => {
    expect(nextTouch(undefined, 2)).toEqual({ type: 'serve', team: 2 });
    expect(nextTouch({ type: 'serve', team: 1 }, 1)).toEqual({ type: 'pass', team: 2 });
    expect(nextTouch({ type: 'pass', team: 2 }, 1)).toEqual({ type: 'set', team: 2 });
    expect(nextTouch({ type: 'set', team: 2 }, 1)).toEqual({ type: 'attack', team: 2 });
    expect(nextTouch({ type: 'attack', team: 2 }, 1)).toEqual({ type: 'dig', team: 1 });
    expect(nextTouch({ type: 'attack', team: 2 }, 1, 0.2)).toEqual({ type: 'block', team: 1 });
    expect(nextTouch({ type: 'attack', team: 2 }, 1, 0.6)).toEqual({ type: 'dig', team: 1 });
    expect(nextTouch({ type: 'relance', team: 1 }, 1)).toEqual({ type: 'dig', team: 2 });
    expect(nextTouch({ type: 'dig', team: 1 }, 1)).toEqual({ type: 'set', team: 1 });
    expect(nextTouch({ type: 'block', team: 1 }, 1)).toEqual({ type: 'dig', team: 1 });
  });
  it("after a point, gives the losing team's touch", () => {
    expect(nextTouch({ type: 'block', team: 1, result: 'point' }, 1)).toEqual({ type: 'dig', team: 2 });
    expect(nextTouch({ type: 'set', team: 1, result: 'point' }, 1)).toEqual({ type: 'dig', team: 2 });
    expect(nextTouch({ type: 'attack', team: 1, result: 'point' }, 1, 0.2)).toEqual({ type: 'block', team: 2 });
    expect(nextTouch({ type: 'serve', team: 1, result: 'point' }, 1)).toEqual({ type: 'pass', team: 2 });
    expect(nextTouch({ type: 'set', team: 1, result: 'error' }, 1)).toEqual({ type: 'attack', team: 1 });
  });
});

describe('nextServer', () => {
  const serve = (team: Group, player: string) => ({ team, player });
  it("keeps the server of a team that kept the serve, else takes the rotation's next", () => {
    expect(nextServer([], 1)).toBeUndefined();
    expect(nextServer([serve(1, '1:4')], 1)).toBe('1:4');
    expect(nextServer([serve(1, '1:4'), serve(2, '2:7')], 1)).toBeUndefined();
    const set = [serve(1, '1:4'), serve(2, '2:7'), serve(1, '1:9'), serve(1, '1:9'), serve(2, '2:3'), serve(1, '1:2'), serve(2, '2:7'), serve(1, '1:4'), serve(2, '2:5')];
    expect(nextServer(set, 1)).toBe('1:9');
    expect(nextServer(set, 2)).toBe('2:5');
    expect(nextServer(set.slice(0, -1), 2)).toBe('2:3');
  });
});

describe('runningScores', () => {
  it('counts each set from 0, a rally of no play or joined to the one before for nothing', () => {
    const scores = runningScores([
      { set: 1, winner: 1, skip: false },
      { set: 1, winner: 2, skip: true },
      { set: 1, winner: 2, skip: false },
      { set: 1, winner: null, skip: false },
      { set: 2, winner: 2, skip: false },
    ]);

    expect(scores).toEqual([[1, 0], null, [1, 1], [1, 1], [0, 1]]);
    expect(offGiven([1, 1, 1, 1, 2], scores, ['1-1', '1-0', null])).toEqual(new Map([[4, '1-0']]));
  });
});

describe('matchFinished', () => {
  it('needs every rally checked and no report open', () => {
    expect(matchFinished([1, 2], [2, 1, 9], 0)).toBe(true);
    expect(matchFinished([1, 2], [1], 0)).toBe(false);
    expect(matchFinished([1, 2], [1, 2], 1)).toBe(false);
  });

  it('is not finished without rallies', () => {
    expect(matchFinished([], [], 0)).toBe(false);
  });
});

describe('joinStart and joinEnd', () => {
  const joins = (k: number) => k === 1 || k === 2;

  it('find both ends of rallies joined in a chain', () => {
    expect([1, 2, 3].map((k) => joinStart(k, joins))).toEqual([1, 1, 1]);
    expect([1, 2, 3].map((k) => joinEnd(k, joins))).toEqual([3, 3, 3]);
  });

  it('leave a rally joined to nothing where it is', () => {
    expect(joinStart(0, joins)).toBe(0);
    expect(joinEnd(4, joins)).toBe(4);
  });
});

describe('unwarnedReports', () => {
  const report = (kind: string | null) => ({ kind });

  it("drops the automatic reports the editor's warnings stand for, with the question left empty", () => {
    expect(unwarnedReports([{ reports: [report('auto.noServe'), report('auto.passWithoutServe')] }])).toEqual([]);
  });

  it('keeps those only the server finds and the viewers', () => {
    const kept = { reports: [report('auto.scoreOff'), report('wrongPlayer')] };
    expect(unwarnedReports([kept])).toEqual([kept]);
    expect(unwarnedReports([{ reports: [report('auto.gap'), report('auto.record.serve')] }])).toEqual([{ reports: [report('auto.record.serve')] }]);
  });
});

describe('liveReports', () => {
  const report = (kind: string | null) => ({ kind });

  it('drops the automatic reports of a joined rally, with the question left empty', () => {
    expect(liveReports([{ rally: 1, reports: [report('auto.noServe')] }], new Set([1]))).toEqual([]);
  });

  it('keeps those on a player and the viewers', () => {
    const reports = [report('auto.gap'), report('auto.sameJersey'), report('wrongPlayer')];
    expect(liveReports([{ rally: 1, reports }], new Set([1]))).toEqual([{ rally: 1, reports: [report('auto.sameJersey'), report('wrongPlayer')] }]);
  });

  it('leaves the other rallies and those in no rally', () => {
    const questions = [
      { rally: 2, reports: [report('auto.gap')] },
      { rally: null, reports: [report('auto.gap')] },
    ];
    expect(liveReports(questions, new Set([1]))).toEqual(questions);
  });
});

describe('closedEnd', () => {
  it('ends a checked rally where its last action lands, at most CLOSE_S after it, never later than it ended', () => {
    expect(closedEnd(20, { time: 10, type: 'attack' }, [5, 11.2, 13])).toBe(11.2);
    expect(closedEnd(20, { time: 10, type: 'attack' }, [14])).toBe(12.5);
    expect(closedEnd(20, { time: 10, type: 'attack' }, [])).toBe(12.5);
    expect(closedEnd(11, { time: 10, type: 'attack' }, [])).toBe(11);
    expect(closedEnd(20, { time: 10, type: 'fault' }, [11])).toBe(10);
    expect(closedEnd(20, undefined, [11])).toBe(20);
  });
});

describe('settled', () => {
  const page = new Map([[100, { type: 'missed', result: 'error', player: '1:4', cause: 0, partner: '' }]]);

  it('takes a touch added that the page holds as a correction of it, what it says beyond the page', () => {
    const added = [
      { frame: 100, team: 1 as const, type: 'missed', result: 'error', player: '1:5' },
      { frame: 200, team: 2 as const, type: 'dig', result: 'play' },
    ];
    expect(settled({ touches: [], added }, page)).toEqual({ touches: [{ frame: 100, player: '1:5' }], added: [added[1]] });
    expect(settled({ touches: [], added: [{ ...added[0], player: '1:4' }] }, page)).toEqual({ touches: [], added: [] });
  });

  it('keeps a correction of that touch saved already', () => {
    const saved = { touches: [{ frame: 100, player: '1:9' }], added: [{ frame: 100, team: 1 as const, type: 'missed', result: 'error', player: '1:5' }] };
    expect(settled(saved, page)).toEqual({ touches: [{ frame: 100, player: '1:9' }], added: [] });
  });
});
