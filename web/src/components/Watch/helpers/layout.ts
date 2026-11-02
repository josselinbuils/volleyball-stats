export const VIEWS = ['video', '2d', '3d', 'tv'] as const;
export type View = (typeof VIEWS)[number];

/** The views shown, in place order. `x` is the left column's share of the width, `y` the top row's of
 * the height, `flip` puts the tall view of three on the right. */
export interface Layout {
  order: View[];
  x: number;
  y: number;
  flip: boolean;
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** A line between views: `ratio` is what it changes, `axis` the screen axis it moves along, `at` its place on
 * that axis, `start` and `length` its span on the other. */
export interface Divider {
  ratio: 'x' | 'y';
  axis: 'x' | 'y';
  at: number;
  start: number;
  length: number;
}

/** A line between two stacked views, at `at` from the top, swapping them. */
export interface SwapLine {
  at: number;
  between: [View, View];
}

export interface Placed {
  rects: Partial<Record<View, Rect>>;
  dividers: Divider[];
  swaps: SwapLine[];
  height: number;
}

/** Pixels between two views. */
export const GAP = 4;
const MIN_RATIO = 0.2;
const FIRST_SHARE = 0.6;
const ASPECT: Record<View, number> = { video: 16 / 9, '2d': 1.75, '3d': 16 / 9, tv: 16 / 9 };

export const clampRatio = (ratio: number) => Math.min(1 - MIN_RATIO, Math.max(MIN_RATIO, ratio));

export const defaultLayout = (order: View[]): Layout => ({ order, x: FIRST_SHARE, y: 0.5, flip: false });

function columns({ order, flip }: Layout): View[][] {
  const [a, b, c, d] = order;
  if (order.length < 2) {
    return [order];
  }
  if (order.length === 2) {
    return [[a], [b]];
  }
  if (order.length === 3) {
    return flip ? [[b, c], [a]] : [[a], [b, c]];
  }
  return [
    [a, c],
    [b, d],
  ];
}

/** The views in two columns, `vertical` turning the whole a quarter for a screen taller than wide. */
export function arrange(layout: Layout, width: number, height: number, vertical = false): Placed {
  const cols = columns(layout);
  const [long, cross] = vertical ? [height, width] : [width, height];
  const n = layout.order.length;
  const rects: Placed['rects'] = {};
  cols.forEach((col, c) => {
    const [u0, u1] = cols.length < 2 ? [0, long] : c === 0 ? [0, long * layout.x] : [long * layout.x, long];
    col.forEach((view, r) => {
      const [v0, v1] = col.length < 2 ? [0, cross] : r === 0 ? [0, cross * layout.y] : [cross * layout.y, cross];
      const place = {
        u: u0 + (u0 > 0 ? GAP / 2 : 0),
        v: v0 + (v0 > 0 ? GAP / 2 : 0),
        us: u1 - u0 - (cols.length > 1 ? GAP / 2 : 0),
        vs: v1 - v0 - (col.length > 1 ? GAP / 2 : 0),
      };
      rects[view] = vertical ? { left: place.v, top: place.u, width: place.vs, height: place.us } : { left: place.u, top: place.v, width: place.us, height: place.vs };
    });
  });
  const dividers: Divider[] = [];
  if (cols.length > 1) {
    dividers.push({ ratio: 'x', axis: vertical ? 'y' : 'x', at: long * layout.x, start: 0, length: cross });
  }
  if (n > 2) {
    const tall = n === 3 ? cols.findIndex((col) => col.length === 2) : null;
    const start = tall === 1 ? long * layout.x : 0;
    const length = tall === null ? long : tall === 0 ? long * layout.x : long * (1 - layout.x);
    dividers.push({ ratio: 'y', axis: vertical ? 'x' : 'y', at: cross * layout.y, start, length });
  }
  return { rects, dividers, swaps: [], height };
}

/** One view under another, each at its own shape: a phone's layout. A taller view would only gain black
 * bands, its width being the limit: the lines between them swap, they do not resize. */
export function stacked(order: View[], width: number): Placed {
  const rects: Placed['rects'] = {};
  const swaps: SwapLine[] = [];
  let top = 0;
  order.forEach((view, k) => {
    const height = width / ASPECT[view];
    rects[view] = { left: 0, top, width, height };
    top += height;
    if (k < order.length - 1) {
      swaps.push({ at: top + GAP / 2, between: [view, order[k + 1]] });
      top += GAP;
    }
  });
  return { rects, dividers: [], swaps, height: top };
}

/** The height showing each view whole in its column, at most `cap`. */
export function pageHeight(layout: Layout, width: number, cap: number): number {
  const cols = columns(layout);
  const natural = cols.map((col, c) => {
    const share = cols.length < 2 ? 1 : c === 0 ? layout.x : 1 - layout.x;
    return col.reduce((sum, view) => sum + (width * share) / ASPECT[view], 0);
  });
  return Math.min(cap, Math.max(...natural));
}

/** The sizes for `layout`'s number of views: the first of two larger, three with their columns level, four equal. */
function balanced(layout: Layout): Layout {
  const [a, b, c] = layout.order;
  if (layout.order.length === 2) {
    return { ...layout, x: FIRST_SHARE };
  }
  if (layout.order.length === 3) {
    const [one, two] = [1 / ASPECT[a], 1 / ASPECT[b] + 1 / ASPECT[c]];
    const tall = two / (one + two);
    return { ...layout, x: layout.flip ? 1 - tall : tall, y: 0.5 };
  }
  return layout.order.length === 4 ? { ...layout, x: 0.5, y: 0.5 } : layout;
}

/** Shows or hides `view`, the sizes starting over; the last one shown stays. */
export function toggled(layout: Layout, view: View): Layout {
  if (!layout.order.includes(view)) {
    return balanced({ ...layout, order: [...layout.order, view] });
  }
  return layout.order.length < 2 ? layout : balanced({ ...layout, order: layout.order.filter((v) => v !== view) });
}

/** `a` and `b` trade places; two views keep their sizes, more trade them with their places. */
export function swapped(layout: Layout, a: View, b: View): Layout {
  const order = layout.order.map((v) => (v === a ? b : v === b ? a : v));
  return { ...layout, order, x: order.length === 2 ? 1 - layout.x : layout.x };
}

/** The two sides of the bar changing `ratio` trade places, each keeping its size. */
export function swappedSides(layout: Layout, ratio: 'x' | 'y'): Layout {
  const [a, b, c, d] = layout.order;
  const n = layout.order.length;
  if (ratio === 'x') {
    const next = { ...layout, x: 1 - layout.x };
    return n === 3 ? { ...next, flip: !layout.flip } : { ...next, order: n === 2 ? [b, a] : [b, a, d, c] };
  }
  return { ...layout, y: 1 - layout.y, order: n === 3 ? [a, c, b] : [c, d, a, b] };
}

/** A layout read back from storage, what `available` cannot show left out; null if it makes no sense. */
export function parsed(stored: unknown, available: readonly View[]): Layout | null {
  const value = stored as Partial<Layout> | null;
  if (!value || !Array.isArray(value.order)) {
    return null;
  }
  const keep = (views: View[]) => [...new Set(views)].filter((v) => available.includes(v));
  const order = keep(value.order);
  if (!order.length) {
    return null;
  }
  const ratio = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? clampRatio(v) : 0.5);
  return { order: order.slice(0, VIEWS.length), x: ratio(value.x), y: ratio(value.y), flip: value.flip === true };
}
