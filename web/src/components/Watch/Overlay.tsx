import { useEffect, useRef, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import type { Ball } from '@/lib/ball';
import { useFormat } from '@/lib/format';
import { contacts } from '@/lib/match';
import { TRAIL_S, ease, onScreen, outBack, shownAt, stamps, statCards, trailAt, type Card, type View } from '@/components/Watch/helpers/overlay';

/** The trail's half width at the ball, as a share of the picture's width on the screen (the ball is about 0.008 wide), and in px at least. */
const WIDTH = 0.003;
const MIN_PX = 1.5;
/** At its oldest end, that share of it. */
const TAIL = 0.3;
/** How opaque the trail is at most, and the seconds behind the ball it takes to get there: the ball itself stays clear. */
const OPACITY = 0.9;
const CLEAR_S = 0.04;
/** A dark edge this wide (px) and this opaque beside the light, which a light wall would hide. */
const EDGE_PX = 1;
const EDGE_OPACITY = 0.25;
/** Its glow, as the films draw it: this many times as wide, this opaque. */
const GLOW = 3;
const GLOW_OPACITY = 0.1;
/** Its colour from its oldest end to the ball, warm as the films' ([r, g, b]). */
const OLD_RGB = [255, 205, 170];
const NEW_RGB = [255, 245, 240];
/** The films' colours: the card's panel, its edge, its numbers once counted. */
const INK = 'rgb(14 16 22 / 0.86)';
const RED = 'rgb(227 6 19)';
const GOLD = 'rgb(255 200 40)';
/** A card slams in over this many seconds, counts its number up over this many, and slides out over this many. */
const IN_S = 0.3;
const COUNT_S = 0.55;
const OUT_S = 0.25;
/** The serve speed that fills the gauge (km/h), as the films'. */
const GAUGE_KMH = 110;
const CARDS = statCards(contacts);

/** Draws the overlay for a view of the picture; the video's zoom calls it each frame, with the view it just set. */
export type Paint = (view: View) => void;

/** The augmented video: the ball's trail drawn on the picture, and each measured serve's speed and attack's height and
 * jump on a card in its corner, as the films show them. Drawn by `paint`, for the frame the video shows (its own clock
 * runs ahead of the picture): paused, it shows that moment. */
export function Overlay({ video, ball, paint }: { video: HTMLVideoElement; ball: Ball; paint: RefObject<Paint | null> }) {
  const { t } = useTranslation();
  const f = useFormat();
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const label = useRef<HTMLSpanElement>(null);
  const value = useRef<HTMLSpanElement>(null);
  const unit = useRef<HTMLSpanElement>(null);
  const gauge = useRef<HTMLDivElement>(null);
  const fill = useRef<HTMLDivElement>(null);
  const below = useRef<HTMLSpanElement>(null);
  // What a card says, its number counted to `count` (0-1): the words follow the page's language.
  const words = useRef<(c: Card, count: number) => { label: string; value: string; unit: string; gauge: number | null; below: string }>(() => ({
    label: '',
    value: '',
    unit: '',
    gauge: null,
    below: '',
  }));
  words.current = ({ contact }, count) => {
    const c = contacts[contact];
    if (c.type === 'serve' && c.speed !== undefined) {
      return { label: t('overlay.speed'), value: f.num(Math.round(c.speed * count)), unit: t('overlay.kmh'), gauge: count * Math.min(1, c.speed / GAUGE_KMH), below: '' };
    }
    const jump = c.jump ? t('overlay.jumpOf', { cm: f.num(Math.round(c.jump * 100)) }) : '';
    if (c.reach) {
      return { label: t('overlay.reach'), value: f.dec(c.reach * count), unit: t('overlay.m'), gauge: null, below: jump };
    }
    return { label: t('overlay.jump'), value: f.num(Math.round((c.jump ?? 0) * 100 * count)), unit: t('overlay.cm'), gauge: null, below: '' };
  };

  useEffect(() => {
    // The time of the frame on screen, where the browser tells it.
    let shown: number | null = null;
    let request = 0;
    const framed = 'requestVideoFrameCallback' in video;
    const onFrame: VideoFrameRequestCallback = (_, frame) => {
      shown = frame.mediaTime;
      request = video.requestVideoFrameCallback(onFrame);
    };
    if (framed) {
      request = video.requestVideoFrameCallback(onFrame);
    }
    let drawn = '';
    paint.current = (view) => {
      const [wrap, surface, panel] = [box.current, canvas.current, card.current];
      const [width, height] = [video.clientWidth, video.clientHeight];
      if (!wrap || !surface || !panel || !video.videoWidth || !width) {
        return;
      }
      const time = shown ?? video.currentTime;
      const ratio = window.devicePixelRatio || 1;
      const key = [time, view.scale, view.x, view.y, width, height, ratio, video.style.opacity].join();
      if (key === drawn) {
        return;
      }
      drawn = key;
      // Faded with the video between a playlist's clips.
      wrap.style.opacity = video.style.opacity;
      if (surface.width !== Math.round(width * ratio) || surface.height !== Math.round(height * ratio)) {
        surface.width = Math.round(width * ratio);
        surface.height = Math.round(height * ratio);
      }
      const ctx = surface.getContext('2d');
      if (!ctx) {
        return;
      }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const screen = onScreen(width, height, video.videoWidth, video.videoHeight, view);
      const trail = trailAt(ball, time);
      const head = Math.max(MIN_PX, WIDTH * screen.unit);
      const spacing = Math.max(1, head / 2);
      const marks = stamps(
        trail.map((p) => ({ ...screen.at(p), age: p.age })),
        spacing,
      );
      // A soft glow, a dark edge for a light wall, then the trail, warm at its old end.
      for (const [pass, wide, most] of [
        ['glow', GLOW, GLOW_OPACITY],
        ['edge', 1, EDGE_OPACITY],
        ['core', 1, OPACITY],
      ] as const) {
        for (const mark of marks) {
          const old = Math.min(1, mark.age / TRAIL_S);
          const radius = wide * head * (1 - (1 - TAIL) * old) + (pass === 'edge' ? EDGE_PX : 0);
          const opacity = most * Math.min(1, mark.age / CLEAR_S) * (1 - old) ** 1.5;
          // Marks overlap: each one's share of the opacity they add up to.
          ctx.globalAlpha = 1 - (1 - opacity) ** (spacing / (2 * radius));
          const [r, g, b] = OLD_RGB.map((v, k) => Math.round(v + (NEW_RGB[k] - v) * (1 - old)));
          ctx.fillStyle = pass === 'edge' ? '#000' : `rgb(${r} ${g} ${b})`;
          ctx.beginPath();
          ctx.arc(mark.x, mark.y, radius, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
      // The card: in with an overshoot, its number counted up, gold once there, then out.
      const now = shownAt(CARDS, time);
      if (!now) {
        panel.style.visibility = 'hidden';
        return;
      }
      const age = time - now.from;
      const count = ease(0, COUNT_S, age);
      const said = words.current(now, count);
      for (const [el, text] of [
        [label.current, said.label],
        [value.current, said.value],
        [unit.current, said.unit],
        [below.current, said.below],
      ] as const) {
        if (el && el.textContent !== text) {
          el.textContent = text;
        }
      }
      if (value.current) {
        value.current.style.color = count >= 1 ? GOLD : 'white';
      }
      if (gauge.current && fill.current) {
        gauge.current.hidden = said.gauge === null;
        fill.current.style.width = `${(said.gauge ?? 0) * 100}%`;
      }
      if (below.current) {
        below.current.hidden = !said.below;
      }
      const away = panel.offsetLeft + panel.offsetWidth + 24;
      const shift = -away * (1 - outBack(age / IN_S)) - away * ease(now.until - OUT_S, now.until, time);
      panel.style.transform = `translateX(${shift}px)`;
      panel.style.visibility = 'visible';
    };
    return () => {
      paint.current = null;
      if (framed) {
        video.cancelVideoFrameCallback(request);
      }
    };
  }, [video, ball, paint]);

  return (
    <div ref={box} aria-hidden className="@container pointer-events-none absolute inset-0 overflow-hidden">
      <canvas ref={canvas} className="absolute inset-0 size-full" />
      <div
        ref={card}
        className="invisible absolute top-[4cqw] left-[3cqw] grid py-[1.2cqw] pr-[3cqw] pl-[2.6cqw] leading-none whitespace-nowrap text-white tabular-nums uppercase"
        style={{ background: INK, clipPath: 'polygon(1.4cqw 0, 100% 0, calc(100% - 1.4cqw) 100%, 0 100%)', minWidth: 'max(7.5rem, 22cqw)' }}
      >
        <span className="absolute inset-y-0 left-0 w-[2.3cqw]" style={{ background: RED, clipPath: 'polygon(1.4cqw 0, 2.3cqw 0, 0.9cqw 100%, 0 100%)' }} />
        <span ref={label} className="text-[max(0.6rem,1.5cqw)] font-semibold tracking-wide text-white/75" />
        <span className="mt-[0.4cqw] flex items-baseline justify-between gap-[1.2cqw]">
          <span ref={value} className="text-[max(1.6rem,5.2cqw)] font-black tracking-tight italic" />
          <span ref={unit} className="text-[max(0.75rem,1.9cqw)] font-bold" />
        </span>
        <div ref={gauge} className="mt-[0.6cqw] h-[max(3px,0.5cqw)] bg-white/25">
          <div ref={fill} className="h-full" style={{ background: GOLD }} />
        </div>
        <span ref={below} className="mt-[0.6cqw] text-[max(0.6rem,1.5cqw)] font-semibold tracking-wide text-white/75" />
      </div>
    </div>
  );
}
