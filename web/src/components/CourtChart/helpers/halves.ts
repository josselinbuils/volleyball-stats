import type { Contact, Rally } from '@/lib/match';

/** The touches with each team on the half it played at the first rally: the touches of a rally
 * played on the other ends turned half a turn around the court's centre, which keeps their zones. */
export function onOwnHalf(contacts: Contact[], rallies: Rally[]): Contact[] {
  return contacts.map((c) => (rallies[c.rally].flipped && c.x !== null && c.y !== null ? { ...c, x: -c.x, y: -c.y } : c));
}
