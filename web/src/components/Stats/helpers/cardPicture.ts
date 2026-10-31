import { CARD_SHADE, shade } from '@/helpers/colors';

/** A FIFA card's shield, in % of its box: notched top, pointed bottom. */
export const SHIELD: [number, number][] = [
  [0, 6],
  [8, 6],
  [14, 3],
  [30, 3],
  [38, 0],
  [50, 2],
  [62, 0],
  [70, 3],
  [86, 3],
  [92, 6],
  [100, 6],
  [100, 87],
  [50, 100],
  [0, 87],
];
/** The card's gold frame, at 135°. */
export const GOLD: [number, string][] = [
  [0, '#fbe38e'],
  [0.45, '#d4a017'],
  [0.55, '#fff1b8'],
  [1, '#b8860b'],
];

type Box = { x: number; y: number; w: number; h: number };

/** A CSS linear gradient at `degrees` over `box` with its `stops`. */
function gradient(g: CanvasRenderingContext2D, box: Box, degrees: number, stops: [number, string][]): CanvasGradient {
  const a = (degrees * Math.PI) / 180;
  const [dx, dy] = [Math.sin(a), -Math.cos(a)];
  const half = (Math.abs(box.w * dx) + Math.abs(box.h * dy)) / 2;
  const [cx, cy] = [box.x + box.w / 2, box.y + box.h / 2];
  const out = g.createLinearGradient(cx - dx * half, cy - dy * half, cx + dx * half, cy + dy * half);
  stops.forEach(([at, colour]) => out.addColorStop(at, colour));
  return out;
}

function shield(g: CanvasRenderingContext2D, box: Box) {
  g.beginPath();
  SHIELD.forEach(([x, y], k) => (k ? g.lineTo : g.moveTo).call(g, box.x + (box.w * x) / 100, box.y + (box.h * y) / 100));
  g.closePath();
}

/** The opacity an element is drawn with, its ancestors' up to `top` included. */
function opacity(element: Element, top: Element): number {
  let out = 1;
  for (let e: Element | null = element; e && e !== top.parentElement; e = e.parentElement) {
    out *= Number(getComputedStyle(e).opacity);
  }
  return out;
}

/** The player card `card` (its frame), drawn `scale` times its size on a canvas from its layout as
 * shown: the shield in gold, its `colour` fading to its CARD_SHADE, the dots, the picture (or the
 * silhouette) fading out at its foot, the lines, the MVP badge and each letter where it stands. */
export function cardPicture(card: HTMLElement, colour: string, scale = 2): HTMLCanvasElement {
  const frame = card.getBoundingClientRect();
  const at = (e: Element): Box => {
    const r = e.getBoundingClientRect();
    return { x: r.left - frame.left, y: r.top - frame.top, w: r.width, h: r.height };
  };
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(frame.width * scale);
  canvas.height = Math.round(frame.height * scale);
  const g = canvas.getContext('2d')!;
  g.scale(scale, scale);
  const all = { x: 0, y: 0, w: frame.width, h: frame.height };
  shield(g, all);
  g.fillStyle = gradient(g, all, 135, GOLD);
  g.fill();

  const face = card.firstElementChild as HTMLElement;
  const inner = at(face);
  const ink = getComputedStyle(face).color;
  g.save();
  shield(g, inner);
  g.clip();
  g.fillStyle = gradient(g, inner, 160, [
    [0, colour],
    [1, shade(colour, CARD_SHADE)],
  ]);
  g.fillRect(inner.x, inner.y, inner.w, inner.h);
  // The dots, fading out along the diagonal like their mask.
  g.fillStyle = ink;
  for (let y = 4.5; y < inner.h; y += 9) {
    for (let x = 4.5; x < inner.w; x += 9) {
      const along = ((x + y) / (inner.w + inner.h)) * 2;
      g.globalAlpha = 0.25 * Math.max(0, 1 - along / 0.65);
      g.beginPath();
      g.arc(inner.x + x, inner.y + y, 1, 0, 2 * Math.PI);
      g.fill();
    }
  }
  g.globalAlpha = 1;

  // The picture, or the silhouette, fading out at its foot.
  const photo = face.querySelector('img');
  const silhouette = face.querySelector('svg[data-silhouette]');
  const holder = photo ?? silhouette;
  if (holder) {
    const box = at(holder);
    const layer = document.createElement('canvas');
    layer.width = Math.round(box.w * scale);
    layer.height = Math.round(box.h * scale);
    const l = layer.getContext('2d')!;
    l.scale(scale, scale);
    if (photo?.complete && photo.naturalWidth) {
      // object-cover, object-top.
      const fit = Math.max(box.w / photo.naturalWidth, box.h / photo.naturalHeight);
      l.drawImage(photo, (photo.naturalWidth - box.w / fit) / 2, 0, box.w / fit, box.h / fit, 0, 0, box.w, box.h);
    } else if (silhouette) {
      l.scale(box.w / 60, box.h / 80);
      l.fillStyle = ink;
      l.globalAlpha = 0.35;
      l.beginPath();
      l.arc(30, 24, 13, 0, 2 * Math.PI);
      l.fill(new Path2D('M4 80C4 57 16 45 30 45S56 57 56 80Z'));
      l.fill();
      l.setTransform(scale, 0, 0, scale, 0, 0);
    }
    l.globalCompositeOperation = 'destination-in';
    l.fillStyle = gradient(l, { x: 0, y: 0, w: box.w, h: box.h }, 180, [
      [photo ? 0.7 : 0.6, 'black'],
      [1, 'transparent'],
    ]);
    l.fillRect(0, 0, box.w, box.h);
    g.drawImage(layer, box.x, box.y, box.w, box.h);
  }

  // The name's rule and the counts' separators.
  g.strokeStyle = ink;
  g.lineWidth = 1;
  for (const e of face.querySelectorAll('[data-rule]')) {
    const box = at(e);
    const bottom = e.getAttribute('data-rule') === 'bottom';
    g.globalAlpha = bottom ? 0.4 : 0.3;
    g.beginPath();
    g.moveTo(box.x + 0.5, bottom ? box.y + box.h - 0.5 : box.y);
    g.lineTo(bottom ? box.x + box.w : box.x + 0.5, box.y + box.h - (bottom ? 0.5 : 0));
    g.stroke();
  }
  g.globalAlpha = 1;
  const badge = face.querySelector('[data-mvp]');
  if (badge) {
    const box = at(badge);
    g.fillStyle = gradient(g, box, 135, GOLD);
    g.beginPath();
    g.roundRect(box.x, box.y, box.w, box.h, box.h / 2);
    g.fill();
  }

  // Each letter where the page shows it: its wrapping, spacing and alignment as laid out.
  const walker = document.createTreeWalker(face, NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent ?? '';
    const parent = node.parentElement;
    // Hidden inside the card only: an open menu hides the whole page from screen readers.
    const hidden = parent?.closest('[aria-hidden="true"], .sr-only');
    if (!text.trim() || !parent || (hidden && face.contains(hidden))) {
      continue;
    }
    const style = getComputedStyle(parent);
    g.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    g.fillStyle = style.color;
    g.globalAlpha = opacity(parent, face);
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    for (let k = 0; k < text.length; k += 1) {
      range.setStart(node, k);
      range.setEnd(node, k + 1);
      const r = range.getBoundingClientRect();
      if (r.width && text[k].trim()) {
        g.fillText(style.textTransform === 'uppercase' ? text[k].toUpperCase() : text[k], r.left - frame.left + r.width / 2, r.top - frame.top + r.height / 2);
      }
    }
  }
  g.restore();
  return canvas;
}
