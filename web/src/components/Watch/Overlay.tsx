import { useEffect, useRef, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import type { Ball } from '@/lib/ball';
import { useFormat } from '@/lib/format';
import { contacts } from '@/lib/match';
import { GAP_S, TRAIL_S, onScreen, placeAt, serveSpeeds, speedAt, stamps, trailAt, type Shown, type View } from '@/components/Watch/helpers/overlay';

/** The trail's half width at the ball, as a share of the picture's width on the screen (the ball is about 0.008 wide), and in px at least. */
const WIDTH = 0.003;
const MIN_PX = 1.5;
/** At its oldest end, that share of it. */
const TAIL = 0.3;
/** How opaque the trail is at most, and the seconds behind the ball it takes to get there: the ball itself stays clear. */
const OPACITY = 0.85;
const CLEAR_S = 0.04;
/** A dark edge this wide (px) and this opaque beside the white, which a light wall would hide. */
const EDGE_PX = 1;
const EDGE_OPACITY = 0.35;
/** Seconds a serve's speed fades in and out. */
const FADE_S = 0.15;
/** The speed's label, from the ball, in px. */
const OFFSET_PX = 12;
const SPEEDS = serveSpeeds(contacts);

/** Draws the overlay for a view of the picture; the video's zoom calls it each frame, with the view it just set. */
export type Paint = (view: View) => void;

/** What the pipeline knows, drawn on the video in its box: the ball's trail, and each measured serve's speed beside the
 * ball. Drawn by `paint`, for the frame the video shows (its own clock runs ahead of the picture). */
export function Overlay({ video, ball, paint }: { video: HTMLVideoElement; ball: Ball; paint: RefObject<Paint | null> }) {
  const { t } = useTranslation();
  const f = useFormat();
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const label = useRef<HTMLSpanElement>(null);
  const text = useRef<(speed: number) => string>(() => '');
  text.current = (speed) => t('kmh', { speed: f.num(speed) });

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
    let labelled: Shown | null = null;
    paint.current = (view) => {
      const [wrap, surface, tag] = [box.current, canvas.current, label.current];
      const [width, height] = [video.clientWidth, video.clientHeight];
      if (!wrap || !surface || !tag || !video.videoWidth || !width) {
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
      for (const [colour, edge, most] of [
        ['#000', EDGE_PX, EDGE_OPACITY],
        ['#fff', 0, OPACITY],
      ] as const) {
        ctx.fillStyle = colour;
        for (const mark of marks) {
          const old = Math.min(1, mark.age / TRAIL_S);
          const radius = head * (1 - (1 - TAIL) * old) + edge;
          const opacity = most * Math.min(1, mark.age / CLEAR_S) * (1 - old) ** 1.5;
          // Marks overlap: each one's share of the opacity they add up to.
          ctx.globalAlpha = 1 - (1 - opacity) ** (spacing / (2 * radius));
          ctx.beginPath();
          ctx.arc(mark.x, mark.y, radius, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
      // The speed follows the ball, at its last place while it is briefly unseen.
      const speed = speedAt(SPEEDS, time);
      const last = trail[trail.length - 1];
      const at = speed && (placeAt(ball, time) ?? (last && last.age < GAP_S ? last : null));
      if (!speed || !at) {
        tag.style.opacity = '0';
        return;
      }
      if (speed !== labelled) {
        labelled = speed;
        tag.textContent = text.current(speed.speed);
      }
      const place = screen.at(at);
      const x = Math.max(4, Math.min(width - tag.offsetWidth - 4, place.x + OFFSET_PX));
      const y = Math.max(4, Math.min(height - tag.offsetHeight - 4, place.y - OFFSET_PX - tag.offsetHeight));
      tag.style.transform = `translate(${x}px, ${y}px)`;
      tag.style.opacity = String(Math.max(0, Math.min(1, (time - speed.from) / FADE_S, (speed.until - time) / FADE_S)));
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
      <span ref={label} className="absolute top-0 left-0 rounded-full bg-black/70 px-2 py-0.5 text-xs font-medium whitespace-nowrap text-white tabular-nums opacity-0" />
    </div>
  );
}
