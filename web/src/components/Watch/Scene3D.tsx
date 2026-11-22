import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { loadBall3d } from '@/lib/ball3d';
import { match, versioned } from '@/lib/match';
import type { Scene, SceneState } from '@/scene3d/scene';
import { Hint } from '@/components/Tip';
import { Button } from '@/components/ui/button';
import { ErrorNote } from '@/components/ErrorNote';
import { explain } from '@/lib/errors';
import { frameSource } from '@/lib/frames';

let loading: Promise<void> | null = null;

/** scene3d.js, beside the page, loaded once on the first 3D view. */
export function loadScene(): Promise<void> {
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = versioned('scene3d.js');
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

/** The 3D scene of the court at the moment `state` describes, turned with the pointer; `onHover`
 * hears of the player under the pointer, null when none or while turning. `vr` offers it in a headset where there is one,
 * `onSelect` hearing of its trigger. */
export function Scene3D({
  state,
  onHover,
  badge = true,
  overlay,
  vr = false,
  onSelect,
}: {
  state: Omit<SceneState, 'colors'>;
  onHover: (key: number | null) => void;
  badge?: boolean;
  overlay?: ReactNode;
  vr?: boolean;
  onSelect?: () => void;
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
  const selected = useRef(onSelect);
  selected.current = onSelect;
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
            onSelect: () => selected.current?.(),
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
