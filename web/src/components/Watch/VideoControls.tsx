import { useEffect, useMemo, useState } from 'react';
import { Maximize, Minimize, Pause, Play, RotateCcw, RotateCw, Snail, Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { clock } from '@/lib/format';
import { match } from '@/lib/match';
import { usePlayer, useVideoTime } from '@/lib/player';
import { useSet } from '@/lib/sets';
import { cn } from '@/lib/utils';
import { span as allowed } from '@/components/Watch/helpers/span';

/** Seconds the skip buttons move the video by. */
const SKIP = 10;

/** The video's controls, its timeline limited to the set the page shows. */
export function VideoControls() {
  const { t } = useTranslation();
  const { video } = usePlayer();
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
    const events = ['play', 'pause', 'volumechange', 'ratechange'] as const;
    events.forEach((e) => video.addEventListener(e, sync));
    document.addEventListener('fullscreenchange', sync);
    video.addEventListener('timeupdate', keep);
    video.addEventListener('seeking', keep);
    sync();
    keep();
    return () => {
      events.forEach((e) => video.removeEventListener(e, sync));
      document.removeEventListener('fullscreenchange', sync);
      video.removeEventListener('timeupdate', keep);
      video.removeEventListener('seeking', keep);
    };
  }, [video, span]);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else if (video?.parentElement?.requestFullscreen) {
      void video.parentElement.requestFullscreen();
    } else {
      // iPhone: only the video itself goes full screen, in the system's player.
      (video as (HTMLVideoElement & { webkitEnterFullscreen?: () => void }) | null)?.webkitEnterFullscreen?.();
    }
  };
  const button = 'inline-flex size-9 max-sm:size-8 shrink-0 items-center justify-center rounded-md outline-none hover:bg-white/15 focus-visible:ring-3 focus-visible:ring-white/70 [&_svg]:size-5';
  const skip = (by: number) => video && (video.currentTime = Math.min(span.end, Math.max(span.start, video.currentTime + by)));
  // A circular arrow with the seconds inside it, as video players draw it.
  const skipButton = (by: number) => (
    <button
      type="button"
      className={cn(button, 'relative', by < 0 && 'max-sm:ml-auto')}
      aria-label={t(by < 0 ? 'backVideo' : 'forwardVideo', { s: SKIP })}
      title={t(by < 0 ? 'backVideo' : 'forwardVideo', { s: SKIP })}
      onClick={() => skip(by)}
    >
      {by < 0 ? <RotateCcw aria-hidden className="size-6!" /> : <RotateCw aria-hidden className="size-6!" />}
      <span aria-hidden className="absolute inset-0 grid place-items-center pt-px text-[8px] font-bold">
        {SKIP}
      </span>
    </button>
  );

  return (
    // On a phone the timeline takes its own row above the buttons.
    <div className="flex flex-wrap items-center gap-x-1 px-2 py-1 text-white">
      <button
        type="button"
        className={button}
        aria-label={t(state.paused ? 'playVideo' : 'pauseVideo')}
        title={t(state.paused ? 'playVideo' : 'pauseVideo')}
        onClick={() => (video?.paused ? void video.play().catch(() => {}) : video?.pause())}
      >
        {state.paused ? <Play aria-hidden className="fill-current" /> : <Pause aria-hidden className="fill-current" />}
      </button>
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
            video.currentTime = Number(e.target.value);
          }
        }}
        aria-label={t('seekVideo')}
        aria-valuetext={clock(time)}
        className="h-9 min-w-0 flex-1 cursor-pointer accent-(--primary) max-sm:order-first max-sm:h-7 max-sm:basis-full"
      />
      {/* A phone's row has no room for it: the timeline shows where the video is. */}
      <span className="shrink-0 px-1 text-sm text-white/75 tabular-nums max-sm:hidden" aria-hidden>
        {clock(span.end)}
      </span>
      {skipButton(-SKIP)}
      {skipButton(SKIP)}
      <button
        type="button"
        className={cn(button, state.slow && 'bg-white/25')}
        aria-pressed={state.slow}
        aria-label={t('slowVideo')}
        title={t('slowVideo')}
        onClick={() => video && (video.playbackRate = state.slow ? 1 : 0.5)}
      >
        <Snail aria-hidden />
      </button>
      <button
        type="button"
        className={button}
        aria-label={t(state.muted ? 'unmuteVideo' : 'muteVideo')}
        title={t(state.muted ? 'unmuteVideo' : 'muteVideo')}
        onClick={() => video && (video.muted = !video.muted)}
      >
        {state.muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
      </button>
      <button type="button" className={button} aria-label={t(state.full ? 'exitFullscreen' : 'fullscreen')} title={t(state.full ? 'exitFullscreen' : 'fullscreen')} onClick={toggleFullscreen}>
        {state.full ? <Minimize aria-hidden /> : <Maximize aria-hidden />}
      </button>
    </div>
  );
}
