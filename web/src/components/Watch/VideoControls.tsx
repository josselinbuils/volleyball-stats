import { useEffect, useMemo, useState, type ReactElement } from 'react';
import { Focus, Maximize, Minimize, Pause, Play, Repeat1, RotateCcw, RotateCw, Snail, Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { clock } from '@/lib/format';
import { match } from '@/lib/match';
import { seek, togglePlay, usePlayer, useVideoTime } from '@/lib/player';
import { useSet } from '@/lib/sets';
import { cn } from '@/lib/utils';
import { span as allowed } from '@/components/Watch/helpers/span';

/** Seconds the skip buttons move the video by. */
const SKIP = 10;

/** The video's controls, its timeline limited to the set the page shows; `light` on a light background. */
export function VideoControls({ light = false, follow, onFollow }: { light?: boolean; follow?: boolean; onFollow?: () => void }) {
  const { t } = useTranslation();
  const { video, loop, setLoop } = usePlayer();
  const { set, rallies } = useSet();
  const span = useMemo(() => allowed(rallies, set === null, match.duration), [rallies, set]);
  // Tenths of a second: enough for the timeline, without a render per frame.
  const time = Math.min(
    span.end,
    Math.max(
      span.start,
      useVideoTime((now) => Math.round(now * 10) / 10),
    ),
  );
  const [state, setState] = useState({
    paused: true,
    muted: false,
    slow: false,
    full: false,
  });

  useEffect(() => {
    if (!video) {
      return;
    }
    const sync = () =>
      setState({
        paused: video.paused,
        muted: video.muted,
        slow: video.playbackRate < 1,
        full: document.fullscreenElement !== null,
      });
    // The video stays inside the allowed stretch: before it, it starts there; past it, it stops.
    const keep = () => {
      if (video.currentTime < span.start - 0.05) {
        video.currentTime = span.start;
      } else if (video.currentTime > span.end) {
        video.pause();
        video.currentTime = span.end;
      }
    };
    // Played from its end, the stretch starts over.
    const restart = () => {
      if (video.currentTime >= span.end - 0.05) {
        video.currentTime = span.start;
      }
    };
    const events = ['play', 'pause', 'volumechange', 'ratechange'] as const;
    events.forEach((e) => video.addEventListener(e, sync));
    document.addEventListener('fullscreenchange', sync);
    video.addEventListener('timeupdate', keep);
    video.addEventListener('seeking', keep);
    video.addEventListener('play', restart);
    sync();
    keep();
    return () => {
      events.forEach((e) => video.removeEventListener(e, sync));
      document.removeEventListener('fullscreenchange', sync);
      video.removeEventListener('timeupdate', keep);
      video.removeEventListener('seeking', keep);
      video.removeEventListener('play', restart);
    };
  }, [video, span]);

  // iPhones put only a video full screen, not the court's replay.
  const fullscreen = !!video?.parentElement?.requestFullscreen || (video !== null && 'webkitEnterFullscreen' in video);
  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else if (video?.parentElement?.requestFullscreen) {
      // A phone turns to landscape, the court's shape, until full screen ends; iPhones cannot lock it.
      video.parentElement
        .requestFullscreen()
        .then(() => {
          if (matchMedia('(pointer: coarse)').matches && Math.min(screen.width, screen.height) < 600) {
            return (screen.orientation as ScreenOrientation & { lock?: (orientation: string) => Promise<void> }).lock?.('landscape');
          }
        })
        .catch(() => {});
    } else {
      // iPhone: only the video itself goes full screen, in the system's player.
      (video as (HTMLVideoElement & { webkitEnterFullscreen?: () => void }) | null)?.webkitEnterFullscreen?.();
    }
  };
  const button = cn(
    'inline-flex size-9 max-sm:size-8 shrink-0 items-center justify-center rounded-md outline-none focus-visible:ring-3 [&_svg]:size-5',
    light ? 'hover:bg-foreground/10 focus-visible:ring-ring/50' : 'hover:bg-white/15 focus-visible:ring-white/70',
  );
  const skip = (by: number) => video && seek(video, Math.min(span.end, Math.max(span.start, video.currentTime + by)));
  // A circular arrow with the seconds inside it, as video players draw it.
  const skipButton = (by: number) => (
    <Tip label={t(by < 0 ? 'backVideo' : 'forwardVideo', { s: SKIP })} full={state.full}>
      <button type="button" className={cn(button, 'relative', by < 0 && 'max-sm:ml-auto')} aria-label={t(by < 0 ? 'backVideo' : 'forwardVideo', { s: SKIP })} onClick={() => skip(by)}>
        {by < 0 ? <RotateCcw aria-hidden className="size-6!" /> : <RotateCw aria-hidden className="size-6!" />}
        <span aria-hidden className="absolute inset-0 grid place-items-center pt-px text-[8px] font-bold">
          {SKIP}
        </span>
      </button>
    </Tip>
  );

  return (
    // On a phone the timeline takes its own row above the buttons. Over the video zoomed on the ball, which runs past its box.
    <div className={cn('flex flex-wrap items-center gap-x-1 px-2 py-1', light ? 'text-foreground' : 'relative z-10 bg-black text-white')}>
      <Tip label={t(state.paused ? 'playVideo' : 'pauseVideo')} full={state.full}>
        <button type="button" className={button} aria-label={t(state.paused ? 'playVideo' : 'pauseVideo')} onClick={() => togglePlay(video)}>
          {state.paused ? <Play aria-hidden className="fill-current" /> : <Pause aria-hidden className="fill-current" />}
        </button>
      </Tip>
      <span className="shrink-0 px-1 text-sm tabular-nums" aria-hidden>
        {clock(time)}
      </span>
      <input
        type="range"
        min={span.start}
        max={span.end}
        step={0.1}
        value={time}
        onChange={(e) => {
          if (video) {
            seek(video, Number(e.target.value));
          }
        }}
        aria-label={t('seekVideo')}
        aria-valuetext={clock(time)}
        className="h-9 min-w-0 flex-1 cursor-pointer accent-(--primary) max-sm:order-first max-sm:h-7 max-sm:basis-full"
      />
      {/* A phone's row has no room for it: the timeline shows where the video is. */}
      <span className={cn('shrink-0 px-1 text-sm tabular-nums max-sm:hidden', light ? 'text-muted-foreground' : 'text-white/75')} aria-hidden>
        {clock(span.end)}
      </span>
      {skipButton(-SKIP)}
      {skipButton(SKIP)}
      <Tip label={t('slowVideo')} full={state.full}>
        <button
          type="button"
          className={cn(button, state.slow && (light ? 'bg-foreground/15' : 'bg-white/25'))}
          aria-pressed={state.slow}
          aria-label={t('slowVideo')}
          onClick={() => video && (video.playbackRate = state.slow ? 1 : 0.5)}
        >
          <Snail aria-hidden />
        </button>
      </Tip>
      <Tip label={t('loopVideo')} full={state.full}>
        <button type="button" className={cn(button, loop && (light ? 'bg-foreground/15' : 'bg-white/25'))} aria-pressed={loop} aria-label={t('loopVideo')} onClick={() => setLoop(!loop)}>
          <Repeat1 aria-hidden />
        </button>
      </Tip>
      {onFollow && (
        <Tip label={t('followBall')} full={state.full}>
          <button type="button" className={cn(button, follow && (light ? 'bg-foreground/15' : 'bg-white/25'))} aria-pressed={follow} aria-label={t('followBall')} onClick={onFollow}>
            <Focus aria-hidden />
          </button>
        </Tip>
      )}
      {/* The court's replay has no sound. */}
      {match.video && (
        <Tip label={t(state.muted ? 'unmuteVideo' : 'muteVideo')} full={state.full}>
          <button type="button" className={button} aria-label={t(state.muted ? 'unmuteVideo' : 'muteVideo')} onClick={() => video && (video.muted = !video.muted)}>
            {state.muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
          </button>
        </Tip>
      )}
      {fullscreen && (
        <Tip label={t(state.full ? 'exitFullscreen' : 'fullscreen')} full={state.full}>
          <button type="button" className={button} aria-label={t(state.full ? 'exitFullscreen' : 'fullscreen')} onClick={toggleFullscreen}>
            {state.full ? <Minimize aria-hidden /> : <Maximize aria-hidden />}
          </button>
        </Tip>
      )}
    </div>
  );
}

/** A control button with `label` in a tooltip above it, inside the full-screen element while there is
 * one (`full`): the page around it is hidden then. */
function Tip({ label, full, children }: { label: string; full: boolean; children: ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="top" sideOffset={4} container={full ? document.fullscreenElement : undefined}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
