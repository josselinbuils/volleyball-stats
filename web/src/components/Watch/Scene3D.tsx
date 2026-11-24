import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { loadBall3d } from '@/lib/ball3d';
import { clock } from '@/lib/format';
import { match, versioned } from '@/lib/match';
import { seek, togglePlay, usePlayer, useVideoTime } from '@/lib/player';
import { useSet } from '@/lib/sets';
import type { Scene, SceneState, VrAction } from '@/scene3d/scene';
import { span as allowed } from '@/components/Watch/helpers/span';
import { useWatchList } from '@/components/Watch/useWatchList';
import { Hint } from '@/components/Tip';
import { Button } from '@/components/ui/button';
import { ErrorNote } from '@/components/ErrorNote';
import { explain } from '@/lib/errors';
import { frameSource } from '@/lib/frames';

let loading: Promise<void> | null = null;

/** scene3d.js, beside the page (online, the site's copy its meta names), loaded once on the first 3D view. */
export function loadScene(): Promise<void> {
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script');
    // Online, the site's one named by its content (`matches.share_code`); beside the page in the review.
    script.src = document.querySelector<HTMLMetaElement>('meta[name="scene3d"]')?.content || versioned('scene3d.js');
    script.onload = () => resolve();
    script.onerror = () => {
      loading = null;
      reject(new Error('scene3d.js'));
    };
    document.head.append(script);
  });
  return loading;
}

let drawable: boolean | undefined;

/** Whether the browser can draw 3D, asked once: each check opens a WebGL context, and past a few
 * the browser drops the oldest, the scene's own. */
export function canDraw3d(): boolean {
  if (drawable === undefined) {
    try {
      const gl = document.createElement('canvas').getContext('webgl2');
      drawable = !!gl;
      gl?.getExtension('WEBGL_lose_context')?.loseContext();
    } catch {
      drawable = false;
    }
  }
  return drawable;
}

let pixel: CanvasRenderingContext2D | null = null;

/** A CSS colour as rgb(): the page's theme mixes oklch and hex, three.js reads neither oklch nor var(). */
function rgb(color: string): string {
  pixel ??= document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  if (!pixel || !color) {
    return '#888888';
  }
  pixel.clearRect(0, 0, 1, 1);
  pixel.fillStyle = color;
  pixel.fillRect(0, 0, 1, 1);
  const [r, g, b] = pixel.getImageData(0, 0, 1, 1).data;
  return `rgb(${r}, ${g}, ${b})`;
}

/** The colours around `element` for the scene: read when asked, its theme can change (full screen's is dark). */
export function sceneColors(element: Element): SceneState['colors'] {
  const css = getComputedStyle(element);
  const get = (name: string) => rgb(css.getPropertyValue(`--${name}`).trim());
  return {
    team: [get('team1'), get('team2')],
    teamText: [get('team1-text'), get('team2-text')],
    floor: get('muted'),
    foreground: get('foreground'),
    primary: get('primary'),
  };
}

/** Whether a VR headset can show the 3D view, asked again when one is plugged in or out. */
function useVrOffered(): boolean {
  const [offered, setOffered] = useState(false);
  useEffect(() => {
    const xr = navigator.xr;
    if (!xr) {
      return;
    }
    let gone = false;
    const ask = () =>
      xr.isSessionSupported('immersive-vr').then(
        (yes) => !gone && setOffered(yes),
        () => !gone && setOffered(false),
      );
    void ask();
    xr.addEventListener('devicechange', ask);
    return () => {
      gone = true;
      xr.removeEventListener('devicechange', ask);
    };
  }, []);
  return offered;
}

// Seconds the panel's buttons move the video by, as the page's.
const SKIP = 10;

/** The video's controls on the headset's panel: its time and state shown there, its presses (and the trigger away from it)
 * acting on the video, as the page's controls do. `act` hears them. */
function VrControls({ scene, act }: { scene: Scene; act: { current: (action: VrAction | 'select') => void } }) {
  const { video } = usePlayer();
  const { set, rallies } = useSet();
  const { entries, at, step } = useWatchList();
  const span = useMemo(() => allowed(rallies, set === null, match.duration), [rallies, set]);
  const time = Math.min(span.end, Math.max(span.start, useVideoTime(Math.floor)));
  const [playing, setPlaying] = useState(!!video && !video.paused);
  useEffect(() => {
    if (!video) {
      return;
    }
    const heard = () => setPlaying(!video.paused);
    heard();
    video.addEventListener('play', heard);
    video.addEventListener('pause', heard);
    return () => {
      video.removeEventListener('play', heard);
      video.removeEventListener('pause', heard);
    };
  }, [video]);
  useEffect(() => {
    scene.panel({ playing, time: `${clock(time)} / ${clock(span.end)}`, share: (time - span.start) / Math.max(1, span.end - span.start) });
  }, [scene, playing, time, span]);
  act.current = (action) => {
    if (!video) {
      return;
    }
    if (action === 'select' || action === 'play') {
      togglePlay(video);
    } else if (typeof action === 'number') {
      seek(video, span.start + action * (span.end - span.start));
    } else if (action === 'back' || action === 'forward') {
      seek(video, Math.min(span.end, Math.max(span.start, video.currentTime + (action === 'back' ? -SKIP : SKIP))));
    } else {
      const by = action === 'next' ? 1 : -1;
      if (entries[at + by]) {
        step(by);
      }
    }
  };
  return null;
}

/** The 3D scene of the court at the moment `state` describes, turned with the pointer; `onHover`
 * hears of the player under the pointer, null when none or while turning. `vr` offers it in a headset where there is one,
 * the video's controls on a panel there. */
export function Scene3D({
  state,
  onHover,
  badge = true,
  overlay,
  vr = false,
}: {
  state: Omit<SceneState, 'colors'>;
  onHover: (key: number | null) => void;
  badge?: boolean;
  overlay?: ReactNode;
  vr?: boolean;
}) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const scene = useRef<Scene | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'failed'>('loading');
  const offered = useVrOffered();
  // In the headset, on the way there, or why it failed.
  const [inVr, setInVr] = useState(false);
  const [opening, setOpening] = useState(false);
  const [vrError, setVrError] = useState<string | null>(null);
  // The headset's presses, heard by `VrControls` while it shows the view.
  const act = useRef<(action: VrAction | 'select') => void>(() => {});
  // The theme, the `dark` class on <html>, or the scene moving into full screen's dark panel (its size changes): it
  // recolours, paused or not.
  const [theme, setTheme] = useState(0);
  useEffect(() => {
    const recolour = () => setTheme((n) => n + 1);
    const observer = new MutationObserver(recolour);
    observer.observe(document.documentElement, { attributeFilter: ['class'] });
    const resized = new ResizeObserver(recolour);
    if (box.current) {
      resized.observe(box.current);
    }
    return () => {
      observer.disconnect();
      resized.disconnect();
    };
  }, []);

  useEffect(() => {
    let gone = false;
    loadBall3d();
    loadScene()
      .then(() => {
        if (!gone && box.current && window.VolleyScene) {
          scene.current = window.VolleyScene.mount(box.current, match.club?.sponsors ?? [], {
            onSession: (session) => {
              // The video's time and the page's loops run on the headset's frames while it shows the view.
              frameSource(session);
              setInVr(!!session);
            },
            onSelect: () => act.current('select'),
            onControl: (action) => act.current(action),
          });
          setStatus('ready');
        }
      })
      .catch(() => setStatus('failed'));
    return () => {
      gone = true;
      frameSource(null);
      scene.current?.dispose();
      scene.current = null;
    };
  }, []);

  // The page's colours, read on every update and theme change.
  useEffect(() => {
    if (status !== 'ready' || !scene.current) {
      return;
    }
    scene.current.update({ ...state, colors: sceneColors(box.current ?? document.documentElement) });
  }, [state, status, theme]);

  return (
    <div className="relative aspect-[16/10] w-full overflow-hidden rounded-md bg-muted/40 [:fullscreen_&]:aspect-auto [:fullscreen_&]:h-full [:fullscreen_&]:rounded-none">
      <div
        ref={box}
        className="absolute inset-0 touch-none [&>canvas]:block [&>canvas]:size-full"
        onPointerMove={(e) => onHover(e.buttons || !scene.current ? null : scene.current.pick(e.clientX, e.clientY))}
        onPointerLeave={() => onHover(null)}
      />
      {inVr && scene.current && <VrControls scene={scene.current} act={act} />}
      {status !== 'ready' && <p className="absolute inset-0 m-0 grid place-items-center text-sm text-muted-foreground">{t(status === 'failed' ? 'scene3d.failed' : 'scene3d.loading')}</p>}
      {overlay}
      {status === 'ready' && (vr || inVr) && offered && (
        // Its own clicks: not the view's, which play or pause.
        <div className="absolute bottom-2 left-2 grid justify-items-start gap-1" onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
          {vrError && <ErrorNote {...explain(t, vrError, 'scene3d.vrFailed')} className="rounded-md bg-card/85 px-2 py-1 text-xs" />}
          <div className="flex items-center gap-1.5 rounded-md bg-card/85 py-1 pr-2 pl-1">
            <Button
              size="sm"
              variant="outline"
              busy={opening}
              onClick={() => {
                if (inVr) {
                  scene.current?.leaveVr();
                  return;
                }
                setVrError(null);
                setOpening(true);
                // Asked at once: the browser opens the headset only within the click.
                scene.current
                  ?.enterVr()
                  .catch((e: unknown) => setVrError(e instanceof Error ? e.message : String(e)))
                  .finally(() => setOpening(false));
              }}
            >
              {t(inVr ? 'scene3d.leaveVr' : 'scene3d.vr')}
            </Button>
            <Hint label={t('scene3d.vrNote')} />
          </div>
        </div>
      )}
      {status === 'ready' && badge && (
        <p className="absolute top-2 right-2 m-0 [:fullscreen_&]:top-auto [:fullscreen_&]:bottom-2 flex max-w-[60%] items-center gap-1.5 rounded-md bg-card/85 px-2 py-1 text-[11px] leading-tight text-muted-foreground">
          {t(match.ball3d ? 'scene3d.badgeFound' : 'scene3d.badge')}
          <Hint label={t(match.ball3d ? 'scene3d.noteFound' : 'scene3d.note')} />
        </p>
      )}
    </div>
  );
}
