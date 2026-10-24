import type { Contact, ZoneCell } from '@/lib/match';

/** The touches in a zone cell: its zone number, on its half of the court. */
export function inCell(c: Contact, cell: ZoneCell): boolean {
  return c.zone === cell.zone && c.x !== null && c.x < 0 === cell.x < 0;
}

/** The touches of each cell, in `cells` order. */
export function cellContacts(contacts: Contact[], cells: ZoneCell[]): Contact[][] {
  return cells.map((cell) => contacts.filter((c) => inCell(c, cell)));
}
