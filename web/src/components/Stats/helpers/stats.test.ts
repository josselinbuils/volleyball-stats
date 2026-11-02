import { describe, expect, it } from 'vitest';
import type { Contact, Person } from '@/lib/match';
import type { Drop } from '@/components/Stats/helpers/between';
import { attackRating, lines, meanAttackRating, meanDigRating, meanRating, meanServeRating, mvp, over, rating, serveRating, unattacked, type Line, type Stats } from '@/components/Stats/helpers/stats';

describe('lines', () => {
  const people: Record<string, Person> = {
    0: { team: 1, number: 1, jersey: null },
    1: { team: 1, number: 2, jersey: null },
    2: { team: 1, number: null, jersey: null },
    3: { team: 2, number: 1, jersey: null },
  };
  // Each touch alone in its rally: no touch follows it.
  let rally = 0;
  const touch = (type: string, g: number, person: number | null, result = 'play', receiver?: number | null) => ({ type, g, person, result, receiver, rally: rally++ }) as Contact;
  const contacts = [
    touch('serve', 1, 0, 'point', 3), // ace on team 2's no. 1
    touch('serve', 2, 3, 'point', 1), // ace on team 1's no. 2
    touch('serve', 2, 3, 'play'),
    touch('pass', 1, 1, 'error'),
    touch('attack', 1, 0, 'point'),
    touch('attack', 1, 2, 'error'), // a track without identity
    touch('dig', 1, 3), // team 2's player on team 1's side: a swapped track
    touch('floor', 1, null),
  ];
  const count = (stats: Record<string, Contact[]>) =>
    Object.fromEntries(
      Object.entries(stats)
        .filter(([, v]) => v.length)
        .map(([k, v]) => [k, v.length]),
    );

  it('counts the touches, points and faults of each player, aces missed included, then the rest and the team', () => {
    const [one, two, rest, total] = lines(contacts, people, 1);
    expect([one.id, two.id, rest.id, total.id]).toEqual([0, 1, 'rest', 'total']);
    expect(count(one.stats)).toEqual({ touches: 2, serves: 1, aces: 1, serveRated: 1, attacks: 1, kills: 1, attackRated: 1, points: 2 });
    expect(count(two.stats)).toEqual({ touches: 1, receptions: 2, missed: 2, rated: 2, faults: 2 });
    expect(count(rest.stats)).toEqual({ touches: 2, attacks: 1, attackFaults: 1, attackRated: 1, digs: 1, faults: 1 });
    expect(count(total.stats)).toEqual({ touches: 5, serves: 1, aces: 1, serveRated: 1, receptions: 2, missed: 2, rated: 2, attacks: 2, kills: 1, attackFaults: 1, attackRated: 2, digs: 1, points: 2, faults: 3 });
  });

  it('makes one player of the identities given one name, shown by the one with the most touches', () => {
    const named: Record<string, Person> = { ...people, 0: { ...people[0], name: 'Lou' }, 1: { ...people[1], name: 'Lou' } };
    const [lou, rest, total] = lines(contacts, named, 1);
    expect([lou.id, rest.id, total.id]).toEqual([0, 'rest', 'total']);
    expect(count(lou.stats)).toEqual({ touches: 3, serves: 1, aces: 1, serveRated: 1, receptions: 2, missed: 2, rated: 2, attacks: 1, kills: 1, attackRated: 1, points: 2, faults: 2 });
  });

  it('counts free balls and their faults', () => {
    const [one] = lines([touch('relance', 1, 0, 'error')], people, 1);
    expect(count(one.stats)).toEqual({ touches: 1, relances: 1, relanceFaults: 1, faults: 1 });
  });

  it('counts the attacks and blocks winning, faulted or played on', () => {
    const [one] = lines([touch('attack', 1, 0, 'play'), touch('block', 1, 0, 'point'), touch('block', 1, 0, 'error'), touch('block', 1, 0, 'play')], people, 1);
    expect(count(one.stats)).toEqual({ touches: 4, attacks: 1, defended: 1, blocks: 3, blockPoints: 1, blockFaults: 1, blockDefended: 1, points: 1, faults: 1 });
  });

  it('counts an ace a reception touched once, as that reception', () => {
    const serve = touch('serve', 2, 3, 'point', 0);
    const pass = { ...touch('pass', 1, 0, 'error'), rally: serve.rally };
    const [one, total] = lines([serve, pass], people, 1);
    expect(count(one.stats)).toEqual({ touches: 1, receptions: 1, missed: 1, rated: 1, faults: 1 });
    expect(count(total.stats)).toEqual({ touches: 1, receptions: 1, missed: 1, rated: 1, faults: 1 });
  });

  it('counts an ace missed by no identified player in the rest', () => {
    const [player, rest] = lines([touch('serve', 1, 0, 'point', 2)], people, 2);
    expect([player.id, count(player.stats)]).toEqual(['rest', { receptions: 1, missed: 1, rated: 1, faults: 1 }]);
    expect(rest.id).toBe('total');
  });

  it('counts an ace the review says no one missed for the team only', () => {
    const [total] = lines([touch('serve', 1, 0, 'point', null)], people, 2);
    expect([total.id, count(total.stats)]).toEqual(['total', { receptions: 1, missed: 1, rated: 1, faults: 1 }]);
  });

  it('counts a ball dropped between two players for each of them, once for the team', () => {
    const landing = touch('floor', 1, null);
    const dropped: Drop[] = [{ landing, pair: [0, 2] }];
    const [one, two, rest, total] = lines([touch('serve', 1, 0), touch('serve', 1, 1), touch('serve', 1, 2), landing], people, 1, dropped);
    expect([one.stats.between, two.stats.between, rest.stats.between, total.stats.between]).toEqual([[landing], [], [landing], [landing]]);
  });

  it('grades the receptions it can rate', () => {
    const at = (type: string, t: number, x: number, y: number) => ({ type, t, x, y, side: 'left', rally: 0, result: 'play' }) as Contact;
    const [one] = lines([{ ...at('pass', 0, -6, 0), g: 1, person: 0 }, at('set', 1.5, -1, 1), { ...at('pass', 3, -6, 0), g: 1, person: 0 }, at('set', 4.5, -6, -3)], people, 1);
    expect(count(one.stats)).toEqual({ touches: 2, receptions: 2, unattacked: 2, rated: 2, perfect: 1, poor: 1 });
    // A perfect one and a poor one: 2 of 3, 3.3 out of 5.
    expect(meanRating(one.stats)).toBeCloseTo(10 / 3);
  });

  it('grades the serves out of 5, a reception lost as high as an ace', () => {
    const [ace, lost, fair, fault] = [0, 1, 2, 3].map((t) => ({ t }) as Contact);
    const s = { serveRated: [ace, lost, fair, fault], aces: [ace], serveTough: [], serveFair: [fair], serveEasy: [], serveFaults: [fault] } as unknown as Stats;
    // An ace, a reception lost, a good reception and a fault: 5, 5, 3 and 0.
    expect(meanServeRating(s)).toBeCloseTo(3.25);
  });
});

describe('rating', () => {
  const touch = (type: string, side: string, t: number, x: number | null, y: number | null, result = 'play', rally = 0) => ({ type, side, t, x, y, result, rally }) as Contact;

  it('grades a reception by how far from the setter’s target its next touch is played', () => {
    const pass = touch('pass', 'left', 0, -6, 0);
    expect(rating(pass, touch('set', 'left', 1.5, -1.5, 1))).toBe(3);
    expect(rating(pass, touch('set', 'left', 1.5, -3, 0))).toBe(2);
    expect(rating(pass, touch('set', 'left', 1.5, -6, -3))).toBe(1);
    // The right half's target is the left one's mirror.
    expect(rating(touch('pass', 'right', 0, 6, 0), touch('set', 'right', 1.5, 1.5, -1))).toBe(3);
  });

  it('gives 1 to a ball sent straight over the net and 0 to a fault', () => {
    expect(rating(touch('pass', 'left', 0, -6, 0), touch('dig', 'right', 1.5, 4, 0))).toBe(1);
    expect(rating(touch('pass', 'left', 0, -6, 0, 'error'), touch('floor', 'left', 1, -7, 0))).toBe(0);
  });

  it('cannot rate without a placed next touch in the rally a second or more later', () => {
    const pass = touch('pass', 'left', 0, -6, 0);
    expect(rating(pass, undefined)).toBeNull();
    expect(rating(pass, touch('serve', 'right', 9, 9, 0, 'play', 1))).toBeNull();
    expect(rating(pass, touch('set', 'left', 0.5, -1, 1.5))).toBeNull();
    expect(rating(pass, touch('set', 'left', 1.5, null, null))).toBeNull();
  });
});

describe('unattacked', () => {
  const touch = (type: string, side: string, rally = 0, result = 'play') => ({ type, side, rally, result }) as Contact;

  it('is a reception or a dig after which its team sent the ball back or lost it without attacking', () => {
    expect(unattacked(touch('pass', 'left'), [touch('set', 'left'), touch('attack', 'left'), touch('dig', 'right')])).toBe(false);
    expect(unattacked(touch('pass', 'left'), [touch('set', 'left'), touch('relance', 'left'), touch('dig', 'right'), touch('attack', 'right')])).toBe(true);
    expect(unattacked(touch('dig', 'left'), [touch('dig', 'right')])).toBe(true);
    expect(unattacked(touch('dig', 'left'), [touch('set', 'left'), touch('floor', 'left')])).toBe(true);
  });

  it('is unknown for a fault, without a next touch in the rally, or for another touch', () => {
    expect(unattacked(touch('pass', 'left', 0, 'error'), [touch('floor', 'left')])).toBe(false);
    expect(unattacked(touch('pass', 'left'), [touch('serve', 'left', 1)])).toBe(false);
    expect(unattacked(touch('set', 'left'), [touch('dig', 'right')])).toBe(false);
  });
});

describe('mvp', () => {
  const line = (id: Line['id'], points: number, faults: number, touches = 0): Line => {
    const many = (n: number) => Array.from({ length: n }, () => ({}) as Contact);
    return { id, stats: { points: many(points), faults: many(faults), touches: many(touches) } as Stats };
  };

  it('picks the best balance of points won minus faults without times, then the most points, then touches', () => {
    const none = () => 0;
    expect(mvp([line(1, 6, 4), line(2, 3, 0), line('total', 20, 0)], none)).toBe(2);
    expect(mvp([line(1, 5, 2), line(2, 4, 1, 30), line(3, 4, 1, 10)], none)).toBe(1);
    expect(mvp([line(2, 4, 1, 10), line(3, 4, 1, 30)], none)).toBe(3);
  });

  it('picks the best balance per minute among those who played at least half the longest time', () => {
    const minutes: Record<number, number> = { 1: 600, 2: 300, 3: 100 };
    const seconds = (p: number) => minutes[p];
    expect(mvp([line(1, 6, 1), line(2, 4, 1), line(3, 3, 0)], seconds)).toBe(2);
    expect(mvp([line(1, 6, 1), line(2, 2, 0)], seconds)).toBe(1);
  });

  it('names no one without a balance above 0', () => {
    expect(mvp([line(1, 2, 2), line(2, 0, 1)], () => 60)).toBeNull();
  });
});

describe('over', () => {
  const touch = (type: string, team: number, rally = 0, result = 'play') => ({ type, team, side: team === 1 ? 'left' : 'right', rally, result }) as Contact;

  it('is a reception or a dig whose next touch is the other team’s', () => {
    expect(over(touch('pass', 1), [touch('dig', 2)])).toBe(true);
    expect(over(touch('dig', 1), [touch('floor', 2), touch('attack', 2)])).toBe(true);
    expect(over(touch('pass', 1), [touch('set', 1), touch('attack', 1)])).toBe(false);
  });

  it('is false for a fault, another touch or none after it in the rally', () => {
    expect(over(touch('pass', 1, 0, 'error'), [touch('dig', 2)])).toBe(false);
    expect(over(touch('set', 1), [touch('dig', 2)])).toBe(false);
    expect(over(touch('pass', 1), [touch('serve', 2, 1)])).toBe(false);
  });
});

describe('serveRating', () => {
  const touch = (type: string, side: string, t: number, x: number | null = null, y: number | null = null, result = 'play') => ({ type, side, t, x, y, result, rally: 0 }) as Contact;

  it('is 4 for an ace, 0 for a fault, else the reception’s grade reversed', () => {
    expect(serveRating(touch('serve', 'right', 0, null, null, 'point'), undefined, undefined)).toBe(4);
    expect(serveRating(touch('serve', 'right', 0, null, null, 'error'), undefined, undefined)).toBe(0);
    const serve = touch('serve', 'right', 0);
    const pass = touch('pass', 'left', 1);
    expect(serveRating(serve, pass, touch('set', 'left', 2.5, -1, 1.5))).toBe(1);
    expect(serveRating(serve, pass, touch('set', 'left', 2.5, -3, 3))).toBe(2);
    expect(serveRating(serve, pass, touch('dig', 'right', 2.5))).toBe(3);
    expect(serveRating(serve, touch('pass', 'left', 1, null, null, 'error'), undefined)).toBe(4);
  });

  it('is null without a reception rated after it', () => {
    expect(serveRating(touch('serve', 'right', 0), touch('dig', 'left', 1), undefined)).toBeNull();
    expect(serveRating(touch('serve', 'right', 0), touch('pass', 'left', 1), undefined)).toBeNull();
  });
});

describe('attackRating', () => {
  function touch(type: Contact['type'], g: 1 | 2, result: Contact['result'] = 'play', rally = 0): Contact {
    return { i: 0, t: 0, type, g, team: g, side: g === 1 ? 'left' : 'right', rally, set: 1, x: 0, y: 0, zone: null, result, person: 1, player: null, name: null };
  }

  it('gives a winner 5, a fault 0 and a block for a point 1', () => {
    expect(attackRating(touch('attack', 1, 'point'), [])).toBe(5);
    expect(attackRating(touch('attack', 1, 'error'), [touch('floor', 2)])).toBe(0);
    expect(attackRating(touch('attack', 1, 'error'), [touch('block', 2, 'point')])).toBe(1);
  });

  it('gives 2 when the other team attacks back before the ball returns, 4 when it does not', () => {
    const attack = touch('attack', 1);
    expect(attackRating(attack, [touch('dig', 2), touch('set', 2), touch('attack', 2)])).toBe(2);
    expect(attackRating(attack, [touch('dig', 2), touch('relance', 2), touch('dig', 1), touch('attack', 1)])).toBe(4);
    expect(attackRating(attack, [touch('dig', 2), touch('relance', 2), touch('dig', 1), touch('attack', 1), touch('attack', 2)])).toBe(4);
  });

  it('leaves unrated an attack with no touch after it in its rally', () => {
    expect(attackRating(touch('attack', 1), [touch('floor', 2)])).toBeNull();
    expect(attackRating(touch('attack', 1), [touch('dig', 2, 'play', 1)])).toBeNull();
  });

  it('feeds the mean of the attacks and of the digs', () => {
    const contacts = [
      touch('attack', 1, 'point', 0),
      touch('attack', 1, 'error', 1),
      touch('block', 2, 'point', 1),
      touch('attack', 1, 'play', 2),
      touch('dig', 2, 'play', 2),
      touch('attack', 2, 'play', 2),
    ];
    const people = { 1: { team: 1, number: 1, jersey: null, name: 'A' } } as const;
    const line = lines(contacts, people as never, 1).find((l) => l.id === 'total');
    expect(line && meanAttackRating(line.stats)).toBeCloseTo((5 + 1 + 2) / 3);
    expect(line && meanDigRating(line.stats)).toBeNull();
  });
});
