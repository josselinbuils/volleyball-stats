import type { Shot } from '@/components/MyMatch/helpers/film';

export const FILM_WIDTH = 720;
export const FILM_HEIGHT = 1280;
const FADE_S = 0.18;
const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
const MARGIN = 44;

/** What the film writes over the picture, in the viewer's language. */
export interface FilmText {
  name: string;
  /** Over the title, under it, and the end's lines. */
  titleAbove: string;
  titleBelow: string;
  endLines: string[];
  replayTag: string;
  primary: string;
  /** What a shot says: the score bar's parts and the touch's name. */
  scoreOf: (time: number) => { left: string; score: string; right: string; set: string } | null;
  action: (shot: Shot) => string;
}

function write(g: CanvasRenderingContext2D, text: string, x: number, y: number, size: number, weight: number, widest: number, color = '#fff'): number {
  let px = size;
  g.font = `${weight} ${px}px ${FONT}`;
  while (g.measureText(text).width > widest && px > 16) {
    px -= 2;
    g.font = `${weight} ${px}px ${FONT}`;
  }
  g.fillStyle = color;
  g.fillText(text, x, y);
  return px;
}

function box(g: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, color: string) {
  g.fillStyle = color;
  g.beginPath();
  g.roundRect(x, y, width, height, 14);
  g.fill();
}

function scoreBar(g: CanvasRenderingContext2D, bar: NonNullable<ReturnType<FilmText['scoreOf']>>) {
  const line = `${bar.left}  ${bar.score}  ${bar.right}`;
  g.font = `700 30px ${FONT}`;
  const width = Math.min(FILM_WIDTH - 2 * MARGIN, g.measureText(line).width + 170);
  box(g, MARGIN, 70, width, 62, 'rgba(0, 0, 0, 0.78)');
  g.textAlign = 'left';
  write(g, line, MARGIN + 20, 112, 30, 700, width - 160);
  g.textAlign = 'right';
  write(g, bar.set, MARGIN + width - 20, 112, 26, 400, 110, 'rgba(255, 255, 255, 0.75)');
  g.textAlign = 'left';
}

function lowerThird(g: CanvasRenderingContext2D, text: FilmText, action: string) {
  const top = FILM_HEIGHT - 250;
  const widest = FILM_WIDTH - 2 * MARGIN - 44;
  box(g, MARGIN, top, FILM_WIDTH - 2 * MARGIN, 136, 'rgba(0, 0, 0, 0.78)');
  g.fillStyle = text.primary;
  g.fillRect(MARGIN + 16, top + 20, 8, 96);
  write(g, text.name, MARGIN + 40, top + 62, 46, 800, widest);
  write(g, action, MARGIN + 40, top + 108, 32, 500, widest, 'rgba(255, 255, 255, 0.85)');
}

function curtain(g: CanvasRenderingContext2D, alpha: number) {
  g.fillStyle = `rgba(0, 0, 0, ${alpha})`;
  g.fillRect(0, 0, FILM_WIDTH, FILM_HEIGHT);
}

function title(g: CanvasRenderingContext2D, text: FilmText) {
  curtain(g, 0.55);
  const widest = FILM_WIDTH - 2 * MARGIN;
  g.textAlign = 'center';
  const middle = FILM_WIDTH / 2;
  write(g, text.titleAbove.toUpperCase(), middle, 540, 34, 600, widest, 'rgba(255, 255, 255, 0.85)');
  write(g, text.name, middle, 650, 108, 800, widest);
  g.fillStyle = text.primary;
  g.fillRect(middle - 70, 690, 140, 10);
  write(g, text.titleBelow, middle, 760, 34, 500, widest, 'rgba(255, 255, 255, 0.85)');
  g.textAlign = 'left';
}

function ending(g: CanvasRenderingContext2D, text: FilmText) {
  curtain(g, 0.72);
  const widest = FILM_WIDTH - 2 * MARGIN;
  const middle = FILM_WIDTH / 2;
  g.textAlign = 'center';
  write(g, text.name, middle, 420, 92, 800, widest);
  g.fillStyle = text.primary;
  g.fillRect(middle - 70, 458, 140, 10);
  text.endLines.forEach((line, k) => write(g, line, middle, 560 + k * 72, 42, 600, widest));
  write(g, text.titleBelow, middle, FILM_HEIGHT - 130, 30, 400, widest, 'rgba(255, 255, 255, 0.75)');
  g.textAlign = 'left';
}

/** Writes over the scene already drawn: the title, the end, or the score and who plays; each shot fading in and out. */
export function writeOver(g: CanvasRenderingContext2D, shot: Shot, time: number, text: FilmText) {
  if (shot.kind === 'intro') {
    title(g, text);
  } else if (shot.kind === 'outro') {
    ending(g, text);
  } else {
    const bar = text.scoreOf(time);
    if (bar) {
      scoreBar(g, bar);
    }
    if (shot.kind === 'replay') {
      g.font = `800 28px ${FONT}`;
      const tag = text.replayTag.toUpperCase();
      const width = g.measureText(tag).width + 36;
      box(g, FILM_WIDTH - MARGIN - width, 148, width, 52, text.primary);
      write(g, tag, FILM_WIDTH - MARGIN - width + 18, 184, 28, 800, width);
    }
    lowerThird(g, text, text.action(shot));
  }
  const edge = Math.min(time - shot.start, shot.start + shot.length - time);
  if (edge < FADE_S) {
    curtain(g, 1 - Math.max(0, edge) / FADE_S);
  }
}
