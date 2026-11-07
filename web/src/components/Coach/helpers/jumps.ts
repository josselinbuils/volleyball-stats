import type { Contact, Group, Person } from '@/lib/match';
import { median } from '@/helpers/median';
import { playerKey } from '@/helpers/players';
import { setAttacks } from '@/helpers/plays';

// Advice from this many measured jumps: a single one is rough (`benchmarks/jumps`).
const JUMPS_FROM = 5;
// Hitting this far from the flight's top loses about 7 cm.
const LATE_MS = 120;
// A jump carrying further towards the net goes forward rather than up.
const DRIFT_M = 0.8;

export const TIPS = ['later', 'earlier', 'up'] as const;
export type JumpTip = (typeof TIPS)[number];

/** A player's advice on their attack jumps, `attacks` the measured ones. */
export interface Jumper {
  person: number;
  tips: JumpTip[];
  attacks: Contact[];
}

/** `g`'s attackers with something to work on in their jumps, from their medians over JUMPS_FROM measured jumps or more
 * on a teammate's set (a setter's dump is no spike): hitting on the way down (jump later) or up (earlier), a jump
 * carrying forward. Most jumps first. No run-up tip: a player's run-up changes too much from match to match
 * (`benchmarks/jumps`). */
export function jumpers(contacts: Contact[], g: Group, people: Record<string, Person>): Jumper[] {
  const by = new Map<string, Contact[]>();
  for (const { set, attack: c } of setAttacks(contacts)) {
    const key = playerKey(c.person, people);
    if (c.g === g && c.late != null && key !== null && key !== playerKey(set.person, people)) {
      by.set(key, [...(by.get(key) ?? []), c]);
    }
  }
  const typical = (values: (number | undefined)[]) => {
    const seen = values.filter((v): v is number => v != null);
    return seen.length >= JUMPS_FROM ? median(seen) : null;
  };
  return [...by.values()]
    .map((attacks) => {
      const [late, drift] = [typical(attacks.map((c) => c.late)), typical(attacks.map((c) => c.drift))];
      const tips: JumpTip[] = [];
      if (late !== null && Math.abs(late) >= LATE_MS) {
        tips.push(late > 0 ? 'later' : 'earlier');
      }
      if (drift !== null && drift > DRIFT_M) {
        tips.push('up');
      }
      return { person: attacks[0].person as number, tips, attacks };
    })
    .filter((j) => j.tips.length > 0)
    .sort((a, b) => b.attacks.length - a.attacks.length);
}
