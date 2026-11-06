import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { loadBall3d } from '@/lib/ball3d';
import { match, versioned } from '@/lib/match';
import type { Scene, SceneState } from '@/scene3d/scene';
import { Tip } from '@/components/Tip';

let loading: Promise<void> | null = null;
// The page's script, read while it runs: scene3d.js sits beside its assets/ folder, which the hosted
// matches share, at the version its own address carries (?v=), else the match's.
const app = document.currentScript instanceof HTMLScriptElement && document.currentScript.src ? new URL(document.currentScript.src) : null;

/** scene3d.js, beside the page's code, loaded once on the first 3D view. */
export function loadScene(): Promise<void> {
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script');
    const v = app?.searchParams.get('v');
    script.src = app ? new URL(v ? `../scene3d.js?v=${v}` : `../${versioned('scene3d.js')}`, app).href : versioned('scene3d.js');
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

/** The page's colours for the scene: read when asked, its theme can change. */
export function sceneColors(): SceneState['colors'] {
  const css = getComputedStyle(document.documentElement);
  const get = (name: string) => rgb(css.getPropertyValue(`--${name}`).trim());
  return {
    team: [get('team1'), get('team2')],
    teamText: [get('team1-text'), get('team2-text')],
    floor: get('muted'),
    foreground: get('foreground'),
    primary: get('primary'),
  };
}

/** The 3D scene of the court at the moment `state` describes, turned with the pointer; `onHover`
 * hears of the player under the pointer, null when none or while turning. */
export function Scene3D({ state, onHover, badge = true, overlay }: { state: Omit<SceneState, 'colors'>; onHover: (key: number | null) => void; badge?: boolean; overlay?: ReactNode }) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const scene = useRef<Scene | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'failed'>('loading');
  // The theme, the `dark` class on <html>: the scene recolours when it changes, paused or not.
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));
  useEffect(() => {
    const observer = new MutationObserver(() => setDark(document.documentElement.classList.contains('dark')));
    observer.observe(document.documentElement, { attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let gone = false;
    loadBall3d();
    loadScene()
      .then(() => {
        if (!gone && box.current && window.VolleyScene) {
          scene.current = window.VolleyScene.mount(box.current, match.brand?.sponsors ?? []);
          setStatus('ready');
        }
      })
      .catch(() => setStatus('failed'));
    return () => {
      gone = true;
      scene.current?.dispose();
      scene.current = null;
    };
  }, []);

  // The page's colours, read on every update and theme change.
  useEffect(() => {
    if (status !== 'ready' || !scene.current) {
      return;
    }
    scene.current.update({ ...state, colors: sceneColors() });
  }, [state, status, dark]);

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
      {status === 'ready' && badge && (
        <Tip label={t(match.ball3d ? 'scene3d.noteFound' : 'scene3d.note')}>
          <p className="absolute top-2 right-2 m-0 [:fullscreen_&]:top-auto [:fullscreen_&]:bottom-2 max-w-[60%] rounded-md bg-card/85 px-2 py-1 text-[11px] leading-tight text-muted-foreground">
            {t(match.ball3d ? 'scene3d.badgeFound' : 'scene3d.badge')}
          </p>
        </Tip>
      )}
    </div>
  );
}
