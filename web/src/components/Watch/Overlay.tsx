import { useEffect, useRef, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import type { Ball } from '@/lib/video';
import { useFormat } from '@/lib/format';
import { contacts, groupName, match, rallies, teamColor, teamRing, type Group } from '@/lib/match';
import { Swatch } from '@/components/Swatch';
import { useVideoTime } from '@/lib/player';
import { TRAIL_S, ease, onScreen, outBack, shownAt, stamps, statCards, trailAt, type Card, type View } from '@/components/Watch/helpers/overlay';
import { justScored, scoreAt } from '@/components/Watch/helpers/score';
import { callAt } from '@/components/Watch/helpers/lineCall';

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
/** A point's number stays gold this long after it lands. */
const LANDED_S = 1.5;
/** The rallies ending on a ball near a line (`web.line_calls`), and their card's time: from this long after the bounce, this long. */
const LINE_CALLS = match.lineCalls;
const CALL_AFTER_S = 0.2;
const CALL_HOLD_S = 2.4;
/** The call's colours: in, out (RED); their words, lighter on the dark card. */
const IN_RGB = 'rgb(22 163 74)';
const IN_TEXT = 'rgb(74 222 128)';
const OUT_TEXT = 'rgb(255 90 90)';
/** The cards' slanted panel and the coloured stripe at its left. */
const CARD_SLANT = 'polygon(1cqw 0, 100% 0, calc(100% - 1cqw) 100%, 0 100%)';
const STRIPE_SLANT = 'polygon(1cqw 0, 1.6cqw 0, 0.6cqw 100%, 0 100%)';
/** The match has a score to show: the score's tower then holds the top left corner. */
export const SCORED = rallies.some((r) => r.score !== null);
/** The tower's place and height in the picture's width (`cqw`, `SIZED`); what shows in that corner too (Watch's title of
 * what plays) goes below it, where the overlay tells the video's box (`--below-tower`, `--tower-left`). */
export const TOWER = 'top-[2.5cqw] left-[2.5cqw] h-[max(1.5rem,3.6cqw)]';
export const BELOW_TOWER = 'top-[var(--below-tower,3rem)] left-[var(--tower-left,0.5rem)]';
/** The box the tower and the cards are sized in (`cqw`): the picture (black bars left out), its left part 80rem wide at
 * most, so a video in full screen on a large screen does not show them as large as the screen (the owner, 15 Nov: the
 * whole width too big on a 1920 px screen, 56rem too small). The whole video's box until the picture is placed: before it
 * loads (`preload="none"`) its poster fills that box. */
const SIZED = '@container absolute inset-0 max-w-[80rem]';

/** Draws the overlay; the video's zoom calls it each frame with where the picture shows the frame of a time: on a copy cut
 * by the automatic zoom, its frames each cut their way. */
export type Paint = (view: (time: number) => View) => void;

/** The augmented video: the ball's trail drawn on the picture, the score in its upper left corner, and each measured
 * serve's speed and attack's speed, height and jump on a card in its lower left corner ("Signaler" and the court's inset
 * hold the others), as the films show them. Drawn by `paint`, for the frame the video shows (its own clock
 * runs ahead of the picture): paused, it shows that moment. */
export function Overlay({ video, ball, paint }: { video: HTMLVideoElement; ball: Ball; paint: RefObject<Paint | null> }) {
  const { t } = useTranslation();
  const f = useFormat();
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const sized = useRef<HTMLDivElement>(null);
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
    const jump = c.jump ? t('overlay.jumpOf', { cm: f.num(Math.round(c.jump * 100)) }) : '';
    const speed = c.type === 'serve' ? c.speed : c.attackSpeed;
    if (speed !== undefined) {
      const below = [c.reach ? t('overlay.reachOf', { m: f.dec(c.reach) }) : '', jump].filter(Boolean).join(' · ');
      return { label: t('overlay.speed'), value: f.num(Math.round(speed * count)), unit: t('overlay.kmh'), gauge: count * Math.min(1, speed / GAUGE_KMH), below };
    }
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
    let placed = '';
    paint.current = (viewAt) => {
      const [wrap, surface, panel] = [box.current, canvas.current, card.current];
      const [width, height] = [video.clientWidth, video.clientHeight];
      if (!wrap || !surface || !panel || !video.videoWidth || !width) {
        return;
      }
      const time = shown ?? video.currentTime;
      const view = viewAt(time);
      const ratio = window.devicePixelRatio || 1;
      const key = [time, view.scale, view.x, view.y, width, height, ratio, video.style.opacity].join();
      if (key === drawn) {
        return;
      }
      drawn = key;
      // Faded with the video between a playlist's clips.
      wrap.style.opacity = video.style.opacity;
      const size = [width, height, video.videoWidth, video.videoHeight].join();
      if (size !== placed && sized.current) {
        placed = size;
        const fit = onScreen(width, height, video.videoWidth, video.videoHeight, { scale: 1, x: 0, y: 0 });
        const [corner, far] = [fit.at({ x: 0, y: 0 }), fit.at({ x: 1, y: 1 })];
        Object.assign(sized.current.style, { left: `${corner.x}px`, top: `${corner.y}px`, width: `${far.x - corner.x}px`, height: `${far.y - corner.y}px` });
        const tower = sized.current.querySelector('[data-tower]')?.getBoundingClientRect();
        const at = wrap.getBoundingClientRect();
        if (tower && wrap.parentElement) {
          wrap.parentElement.style.setProperty('--below-tower', `${tower.bottom - at.top + 8}px`);
          wrap.parentElement.style.setProperty('--tower-left', `${tower.left - at.left}px`);
        }
      }
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
    <div ref={box} aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <canvas ref={canvas} className="absolute inset-0 size-full" />
      <div ref={sized} className={SIZED}>
        {SCORED && <Tower />}
        {LINE_CALLS.length > 0 && <Call />}
        <div
          ref={card}
          className="invisible absolute bottom-[3cqw] left-[2.5cqw] grid py-[0.8cqw] pr-[2cqw] pl-[1.8cqw] leading-none whitespace-nowrap text-white tabular-nums uppercase"
          style={{ background: INK, clipPath: CARD_SLANT, minWidth: 'max(5rem, 14.5cqw)' }}
        >
          <span className="absolute inset-y-0 left-0 w-[1.6cqw]" style={{ background: RED, clipPath: STRIPE_SLANT }} />
          <span ref={label} className="text-[max(0.5rem,1cqw)] font-semibold tracking-wide text-white/75" />
          <span className="mt-[0.3cqw] flex items-baseline justify-between gap-[0.8cqw]">
            <span ref={value} className="text-[max(1.05rem,3.4cqw)] font-black tracking-tight italic" />
            <span ref={unit} className="text-[max(0.55rem,1.25cqw)] font-bold" />
          </span>
          <div ref={gauge} className="mt-[0.4cqw] h-[max(2px,0.35cqw)] bg-white/25">
            <div ref={fill} className="h-full" style={{ background: GOLD }} />
          </div>
          <span ref={below} className="mt-[0.4cqw] text-[max(0.5rem,1cqw)] font-semibold tracking-wide text-white/75" />
        </div>
      </div>
    </div>
  );
}

/** A slanted piece of the tower. */
const SLANT = { clipPath: 'polygon(0.7cqw 0, 100% 0, calc(100% - 0.7cqw) 100%, 0 100%)' };

/** The score as the films' timing tower: the teams, their points (the one just won gold) and the set; on a narrow video
 * the teams' colours alone, outlined as on a dark page. */
function Tower() {
  const { t } = useTranslation();
  const f = useFormat();
  const shown = useVideoTime((time) => {
    const now = scoreAt(rallies, time, match.scores);
    return now && `${now.set}:${now.score[0]}:${now.score[1]}:${justScored(rallies, time, LANDED_S) ?? 0}`;
  });
  if (!shown) {
    return null;
  }
  const [set, one, two, landed] = shown.split(':').map(Number);
  const team = (g: Group) => (
    <span className="relative flex items-center gap-[0.8cqw] py-0 pr-[1.4cqw] pl-[1.2cqw]" style={{ ...SLANT, background: INK }}>
      <Swatch color={teamColor(g)} ring={teamRing(g)} className="size-[max(0.5rem,1.1cqw)]" />
      <span className="max-w-[16cqw] truncate text-[max(0.6rem,1.3cqw)] font-bold @max-md:hidden">{groupName(t, g)}</span>
    </span>
  );
  const points = (g: Group, n: number) => (
    <span
      className="grid min-w-[max(1.7rem,3.9cqw)] place-items-center px-[0.9cqw] text-[max(0.85rem,2cqw)] font-black italic"
      style={{ ...SLANT, background: landed === g ? GOLD : 'rgb(60 60 60 / 0.92)', color: landed === g ? INK : 'white' }}
    >
      {f.num(n)}
    </span>
  );
  return (
    <div data-tower className={`dark absolute ${TOWER} flex items-stretch gap-[0.2cqw] leading-none whitespace-nowrap text-white tabular-nums uppercase`}>
      {team(1)}
      {points(1, one)}
      {points(2, two)}
      {team(2)}
      <span className="grid place-items-center px-[1.3cqw] text-[max(0.55rem,1.1cqw)] font-semibold tracking-wide text-white/75" style={{ ...SLANT, background: INK }}>
        {t('set', { n: f.num(set) })}
      </span>
    </div>
  );
}

/** The close call on screen, as the measured numbers' card: in or out in its colour, the line it is told against when the
 * measure agrees, and the referee's mistake when the review says so; at the bottom's middle, clear of the corners' cards (on
 * a narrow video in its right corner). It slams in with the cards' overshoot while the hosted video holds the bounce. */
function Call() {
  const { t } = useTranslation();
  const shown = useVideoTime((time) => callAt(LINE_CALLS, rallies, time, CALL_AFTER_S, CALL_HOLD_S));
  if (!shown) {
    return null;
  }
  const colour = shown.in ? IN_RGB : RED;
  return (
    <div className="absolute inset-x-0 bottom-[3cqw] flex justify-center @max-md:justify-end @max-md:pr-[2.5cqw]">
      <div
        key={shown.rally}
        className="relative grid animate-in py-[0.8cqw] pr-[2cqw] pl-[2.4cqw] leading-none whitespace-nowrap text-white uppercase duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] fade-in slide-in-from-bottom-8"
        style={{ background: INK, clipPath: CARD_SLANT }}
      >
        <span className="absolute inset-y-0 left-0 w-[1.6cqw]" style={{ background: colour, clipPath: STRIPE_SLANT }} />
        {shown.mark && <span className="text-[max(0.5rem,1cqw)] font-semibold tracking-wide text-white/75">{t(shown.mark.line === 'end' ? 'overlay.endLine' : 'overlay.sideLine')}</span>}
        <span className="mt-[0.3cqw] text-[max(1.05rem,3.4cqw)] font-black tracking-tight italic" style={{ color: shown.in ? IN_TEXT : OUT_TEXT }}>
          {t(shown.in ? 'overlay.in' : 'overlay.out')}
        </span>
        {shown.wrongCall && (
          <span className="mt-[0.5cqw] px-[0.6cqw] py-[0.35cqw] text-center text-[max(0.5rem,1cqw)] font-bold tracking-wide" style={{ background: GOLD, color: INK }}>
            {t('overlay.wrongCall')}
          </span>
        )}
      </div>
    </div>
  );
}
