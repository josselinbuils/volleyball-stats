import * as THREE from 'three';

/** What a press on the panel asks: a button's action, or a number, the share of the timeline to go to. */
export type VrAction = 'previous' | 'back' | 'play' | 'forward' | 'next' | number;

/** What the panel shows: whether the video plays, its time as said on the page, and its share of the timeline. */
export interface VrPanelState {
  playing: boolean;
  time: string;
  share: number;
}

const BUTTONS = ['previous', 'back', 'play', 'forward', 'next'] as const;
// The canvas: the buttons' row, then the timeline from BAR_X to BAR_END and the time after it.
const W = 640;
const H = 200;
const ROW = 130;
const BAR_X = 28;
const BAR_END = 400;
const BAR_Y = 165;
// The panel's width in metres, about a phone's.
const WIDTH_M = 0.22;

/** The video's controls in the headset, on a hand: previous and next rally, 10 s back and forward, play and pause, the
 * timeline. `at` tells which action a point of it (its uv) asks. */
export function vrPanel() {
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(WIDTH_M, (WIDTH_M * H) / W), new THREE.MeshBasicMaterial({ map: texture, transparent: true }));
  mesh.renderOrder = 4;
  let state: VrPanelState = { playing: false, time: '', share: 0 };
  let hovered: string | null = null;

  const paint = () => {
    const g = canvas.getContext('2d')!;
    g.clearRect(0, 0, W, H);
    g.fillStyle = 'rgba(24, 24, 27, 0.9)';
    g.beginPath();
    g.roundRect(0, 0, W, H, 28);
    g.fill();
    const cell = W / BUTTONS.length;
    BUTTONS.forEach((name, k) => {
      const cx = cell * k + cell / 2;
      const cy = ROW / 2 + 6;
      if (hovered === name) {
        g.fillStyle = 'rgba(255, 255, 255, 0.2)';
        g.beginPath();
        g.arc(cx, cy, 50, 0, Math.PI * 2);
        g.fill();
      }
      g.fillStyle = g.strokeStyle = '#fff';
      g.lineWidth = 8;
      const triangle = (x: number, toRight: boolean, size: number) => {
        g.beginPath();
        g.moveTo(x + (toRight ? -size / 2 : size / 2), cy - size * 0.6);
        g.lineTo(x + (toRight ? size / 2 : -size / 2), cy);
        g.lineTo(x + (toRight ? -size / 2 : size / 2), cy + size * 0.6);
        g.closePath();
        g.fill();
      };
      if (name === 'previous' || name === 'next') {
        const right = name === 'next';
        triangle(cx + (right ? -6 : 6), right, 36);
        g.fillRect(cx + (right ? 14 : -22), cy - 22, 8, 44);
      } else if (name === 'play') {
        if (state.playing) {
          g.fillRect(cx - 18, cy - 24, 12, 48);
          g.fillRect(cx + 6, cy - 24, 12, 48);
        } else {
          triangle(cx + 4, true, 44);
        }
      } else {
        g.font = '600 34px system-ui, sans-serif';
        g.textAlign = 'center';
        g.textBaseline = 'middle';
        g.fillText(name === 'back' ? '−10' : '+10', cx, cy);
      }
    });
    g.fillStyle = 'rgba(255, 255, 255, 0.3)';
    g.fillRect(BAR_X, BAR_Y - 5, BAR_END - BAR_X, hovered === 'bar' ? 14 : 10);
    g.fillStyle = '#fff';
    g.fillRect(BAR_X, BAR_Y - 5, (BAR_END - BAR_X) * state.share, hovered === 'bar' ? 14 : 10);
    g.font = '500 30px system-ui, sans-serif';
    g.textAlign = 'left';
    g.textBaseline = 'middle';
    g.fillText(state.time, BAR_END + 24, BAR_Y + 1);
    texture.needsUpdate = true;
  };
  paint();

  return {
    mesh,
    set(next: VrPanelState) {
      if (next.playing !== state.playing || next.time !== state.time || Math.abs(next.share - state.share) > 0.001) {
        state = next;
        paint();
      }
    },
    /** The action under `uv`, null between them. */
    at(uv: THREE.Vector2): VrAction | null {
      const [x, y] = [uv.x * W, (1 - uv.y) * H];
      if (y < ROW) {
        return BUTTONS[Math.min(BUTTONS.length - 1, Math.floor((x / W) * BUTTONS.length))];
      }
      const share = (x - BAR_X) / (BAR_END - BAR_X);
      return share > -0.03 && share < 1.03 ? Math.min(1, Math.max(0, share)) : null;
    },
    /** Lights the action pointed at (null: none). */
    hover(action: VrAction | null) {
      const name = action === null ? null : typeof action === 'number' ? 'bar' : action;
      if (name !== hovered) {
        hovered = name;
        paint();
      }
    },
    dispose() {
      texture.dispose();
      mesh.geometry.dispose();
      mesh.material.dispose();
    },
  };
}
