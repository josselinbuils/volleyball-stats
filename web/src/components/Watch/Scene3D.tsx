import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Scene, SceneState } from '@/scene3d/scene';

let loading: Promise<void> | null = null;

/** scene3d.js, beside the page, loaded once on the first 3D view. */
function load(): Promise<void> {
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'scene3d.js';
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

/** The 3D scene of the court at the moment `state` describes, turned with the pointer; `onHover`
 * hears of the player under the pointer, null when none or while turning. */
export function Scene3D({ state, onHover }: { state: Omit<SceneState, 'colors'>; onHover: (key: number | null) => void }) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const scene = useRef<Scene | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'failed'>('loading');

  useEffect(() => {
    let gone = false;
    load()
      .then(() => {
        if (!gone && box.current && window.VolleyScene) {
          scene.current = window.VolleyScene.mount(box.current);
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

  // The page's colours, read on every update: the theme can change at any time.
  useEffect(() => {
    if (status !== 'ready' || !scene.current) {
      return;
    }
    const css = getComputedStyle(document.documentElement);
    const get = (name: string) => rgb(css.getPropertyValue(`--${name}`).trim());
    scene.current.update({
      ...state,
      colors: {
        team: [get('team1'), get('team2')],
        teamText: [get('team1-text'), get('team2-text')],
        court: get('court'),
        floor: get('muted'),
        line: get('court-line'),
        foreground: get('foreground'),
        primary: get('primary'),
      },
    });
  }, [state, status]);

  return (
    <div className="relative aspect-[16/10] w-full overflow-hidden rounded-md bg-muted/40">
      <div
        ref={box}
        className="absolute inset-0 touch-none [&>canvas]:block [&>canvas]:size-full"
        onPointerMove={(e) => onHover(e.buttons || !scene.current ? null : scene.current.pick(e.clientX, e.clientY))}
        onPointerLeave={() => onHover(null)}
      />
      {status !== 'ready' && <p className="absolute inset-0 m-0 grid place-items-center text-sm text-muted-foreground">{t(status === 'failed' ? 'scene3d.failed' : 'scene3d.loading')}</p>}
      {status === 'ready' && (
        <p className="absolute top-2 right-2 m-0 max-w-[60%] rounded-md bg-card/85 px-2 py-1 text-[11px] leading-tight text-muted-foreground" title={t('scene3d.note')}>
          {t('scene3d.badge')}
        </p>
      )}
    </div>
  );
}
