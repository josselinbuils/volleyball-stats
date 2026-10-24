import type { Contact, Rally } from '@/lib/match';

/** Per rally, whether it was played on the other ends than the reference rally: the match's first,
 * or with `set` that set's first, so that only a deciding set's swap at 8 points counts. */
export function flips(rallies: Rally[], set: number | null): boolean[] {
  const first = rallies.find((r) => set === null || r.set === set);
  return rallies.map((r) => first !== undefined && r.left !== first.left);
}

/** The touches of the `flipped` rallies turned half a turn around the court's centre, which keeps
 * their zones; the others as they are. */
export function onOwnHalf(contacts: Contact[], flipped: boolean[]): Contact[] {
  return contacts.map((c) => (flipped[c.rally] && c.x !== null && c.y !== null ? { ...c, x: -c.x, y: -c.y } : c));
}
