import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { loadBall, useBall } from '@/lib/ball';
import { useFormat } from '@/lib/format';
import { match } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { Feedback } from '@/components/Watch/Feedback';
import { ballAt, zoomOn } from '@/components/Watch/helpers/zoom';

// Share of the way to the zoom's target covered each frame: the view follows the ball within a fifth of a second.
const EASE = 0.1;
// What web.py's --av1-video takes: 1080p, 8-bit, level 4.0; a browser that cannot play it takes the H.264 copy.
const AV1 = 'video/mp4; codecs="av01.0.08M.08"';
const BIG = match.av1 && document.createElement('video').canPlayType(AV1) ? match.av1 : match.video;
// Wider than this on the screen (in its pixels), the 720p copy would be stretched: the player takes the 1080p one.
const WIDE_PX = 1600;

/** The match's video filling its view. `follow` zooms on the ball; `big` asks for the 1080p copy whatever its
 * size; `shown` is false while the view is hidden, the video still setting the page's time. */
export function VideoPanel({ follow, big, shown }: { follow: boolean; big: boolean; shown: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { video, setVideo, playlist } = usePlayer();
  const zoom = follow && shown;
  // Zoomed on the ball, the view eases toward it each frame, back to the whole picture when off or
  // with no ball near.
  const ball = useBall();
  const view = useRef({ scale: 1, x: 0, y: 0 });
  useEffect(() => {
    if (zoom) {
      loadBall();
    }
  }, [zoom]);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement)) {
      return;
    }
    const now = view.current;
    let frame = 0;
    const tick = () => {
      const at = zoom && typeof ball === 'object' ? ballAt(ball, video.currentTime) : null;
      const target = at && video.videoWidth ? zoomOn(at, video.clientWidth, video.clientHeight, video.videoWidth, video.videoHeight) : { scale: 1, x: 0, y: 0 };
      for (const k of ['scale', 'x', 'y'] as const) {
        now[k] += (target[k] - now[k]) * EASE;
      }
      if (!zoom && Math.abs(now.scale - 1) < 0.002) {
        Object.assign(now, { scale: 1, x: 0, y: 0 });
        video.style.transform = '';
        return;
      }
      video.style.transformOrigin = '0 0';
      video.style.transform = `translate(${now.x}px, ${now.y}px) scale(${now.scale})`;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [video, zoom, ball]);
  // A playlist's next clip loads once the video has reached the one it plays: both at once would
  // slow its start.
  const [reached, setReached] = useState<typeof playlist>(null);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement) || !playlist) {
      return;
    }
    const on = () => setReached(playlist);
    video.addEventListener('seeked', on);
    return () => video.removeEventListener('seeked', on);
  }, [video, playlist]);
  // The 720p copy while the picture is small; the 1080p one when asked, zoomed on the ball or wide.
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement)) {
      return;
    }
    const observer = new ResizeObserver(() => setWide(Math.min(video.clientWidth, (video.clientHeight * 16) / 9) * devicePixelRatio > WIDE_PX));
    observer.observe(video);
    return () => observer.disconnect();
  }, [video]);
  const src = match.small && !big && !zoom && !wide ? match.small : BIG;
  // A copy taking over carries on where the video stands, playing if it was.
  useEffect(() => {
    if (!(video instanceof HTMLVideoElement) || !src || video.getAttribute('src') === src) {
      return;
    }
    const { readyState, currentTime, paused } = video;
    video.src = src;
    if (readyState > 0) {
      video.preload = 'auto';
      video.currentTime = currentTime;
      if (!paused) {
        video.play().catch(() => {});
      }
    }
  }, [video, src]);

  return (
    <>
      {shown && <Feedback />}
      {playlist && reached === playlist && playlist.at + 1 < playlist.clips.length && <Preload src={src} time={playlist.clips[playlist.at + 1].start} />}
      {/* What plays, over the video: the bar below is out of sight from the stats and in full screen. */}
      {playlist && (
        <span
          aria-hidden
          className="pointer-events-none absolute top-2 left-2 z-10 max-w-[calc(100%-8.5rem)] truncate rounded-full bg-black/60 px-3 py-1.5 text-sm font-medium text-white backdrop-blur-sm"
        >
          {`${playlist.title(t)} · ${t('iOfN', { i: f.num(playlist.at + 1), n: f.num(playlist.clips.length) })}`}
        </span>
      )}
      {/* Nothing loads before the video is first played or moved (`seek`). */}
      <video ref={setVideo} poster={match.poster} playsInline preload="none" aria-label={t('video')} className="block size-full cursor-pointer" />
    </>
  );
}

/** A hidden copy of the video (`src`, the copy playing) waiting at `time`, the next clip's start:
 * the browser keeps what it fetches for the video, which then jumps there without waiting. */
function Preload({ src, time }: { src: string | null; time: number }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (ref.current) {
      ref.current.currentTime = time;
    }
  }, [time]);
  return <video ref={ref} src={src ?? undefined} muted playsInline preload="auto" aria-hidden className="hidden" />;
}
