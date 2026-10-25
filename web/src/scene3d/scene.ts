import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { Sponsor } from '@/lib/match';

/** A point of the scene in court metres: x along the court (net at 0), y across it (towards the
 * camera positive), h above the floor. */
export interface Point3 {
  x: number;
  y: number;
  h: number;
}

/** What the scene shows at a moment. Colours are CSS colours. */
export interface SceneState {
  /** `tip` names the player under the pointer, shown above them. */
  players: { key: number; x: number; y: number; jump: number; team: 1 | 2; label: string; tip?: string }[];
  ball: Point3 | null;
  trail: Point3[];
  rings: { x: number; y: number; f: number }[];
  landings: { x: number; y: number; f: number }[];
  /** The hall's scoreboard: the teams, team 1 first, their points and the set; null before the first rally. */
  board: { teams: [string, string]; score: [number, number]; set: string } | null;
  colors: { team: [string, string]; teamText: [string, string]; floor: string; foreground: string; primary: string };
}

export interface Scene {
  update: (state: SceneState) => void;
  /** The key of the player at a point of the page, if any. */
  pick: (clientX: number, clientY: number) => number | null;
  dispose: () => void;
}

// The camera's direction, from the stand behind the camera's sideline, a little to the left so the
// net shows in perspective, and the point it looks at; the pointer turns it around that point.
const EYE = new THREE.Vector3(-3.5, 7.5, 15.5);
const TARGET = new THREE.Vector3(0.5, 0.6, 0);
// What the first view holds whatever the view's shape: the court with half a metre behind its end lines,
// the net posts, inside FIT of the view's half width and height.
const FRAMED = [-9.5, 9.5].flatMap((x) => [-5, 5].map((y) => new THREE.Vector3(x, 0, y))).concat([-5, 5].map((y) => new THREE.Vector3(0, 2.6, y)));
const FIT = 0.96;
const NET_TOP = 2.35;
// The trail spans the ball's last TRAIL_S (the page's trail3dAt); it shows from SLOW m/s and is
// full from FAST: a set flies at 5-8 m/s, a serve or an attack at 12-25.
const TRAIL_S = 0.35;
const SLOW = 4;
const FAST = 14;
// Twice the real ball's radius, to follow it at a glance as on the top view.
const BALL_R = 0.21;

// Court metres to the scene's axes: x, height up, y towards the viewer.
const at = (x: number, y: number, h = 0) => new THREE.Vector3(x, h, y);

/** A number painted on a sprite, facing the camera. */
function badge(text: string, background: string, color: string): THREE.Sprite {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const g = canvas.getContext('2d')!;
  g.fillStyle = background;
  g.beginPath();
  g.arc(64, 64, 60, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = color;
  g.font = 'bold 64px system-ui, sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(text, 64, 68);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false }));
  sprite.scale.set(0.55, 0.55, 1);
  sprite.renderOrder = 2;
  return sprite;
}

// The hovered player's name: its height on screen in pixels.
const TIP_PX = 26;

// The figures' skin, and hair colours given out by player key: made up, not the players' own.
const SKIN = 0xe2b48e;
const HAIRS = [0x2b1d14, 0x4a2f1d, 0x6e4a2a, 0x161210, 0xa7834f];

// Spectators' shirts, a crowd's mix.
const CROWD = [0xc0392b, 0x2e86c1, 0x27ae60, 0xf1c40f, 0x8e44ad, 0xe67e22, 0x7f8c8d, 0xecf0f1, 0x34495e];

/** A wooden court: planks of varied shades with dark joints. */
function wood(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 512;
  const g = canvas.getContext('2d')!;
  let seed = 7;
  const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  for (let row = 0; row < 16; row++) {
    for (let x = -random() * 256; x < 512; x += 192 + random() * 128) {
      const shade = 0.9 + random() * 0.14;
      g.fillStyle = `rgb(${Math.round(214 * shade)}, ${Math.round(172 * shade)}, ${Math.round(122 * shade)})`;
      g.fillRect(x, row * 32, 320, 32);
      g.fillStyle = 'rgba(90, 60, 30, 0.35)';
      g.fillRect(x, row * 32, 2, 32);
    }
    g.fillStyle = 'rgba(90, 60, 30, 0.3)';
    g.fillRect(0, row * 32, 512, 1);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  // One canvas is 4 m of floor, its planks 25 cm wide.
  texture.repeat.set(18 / 4, 9 / 4);
  return texture;
}

/** A canvas of `width` × `height` pixels drawn by `paint`, as a texture. */
function painted(width: number, height: number, paint: (g: CanvasRenderingContext2D) => void): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  paint(canvas.getContext('2d')!);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** A window: pale sky panes in a dark frame. */
const windowPanes = () =>
  painted(240, 140, (g) => {
    g.fillStyle = '#2b2f36';
    g.fillRect(0, 0, 240, 140);
    for (let col = 0; col < 4; col++) {
      for (let row = 0; row < 2; row++) {
        const sky = g.createLinearGradient(0, row * 64, 0, row * 64 + 58);
        sky.addColorStop(0, '#ffffff');
        sky.addColorStop(1, '#dce9f7');
        g.fillStyle = sky;
        g.fillRect(8 + col * 58, 8 + row * 64, 52, 58);
      }
    }
  });

/** Paints the hall's scoreboard on `canvas`: each team's name over its points, the set between them;
 * dashes without a score. */
function paintScoreboard(canvas: HTMLCanvasElement, board: SceneState['board']) {
  const g = canvas.getContext('2d')!;
  g.fillStyle = '#1d2a4a';
  g.fillRect(0, 0, 600, 280);
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillStyle = '#ffffff';
  g.font = 'bold 40px system-ui, sans-serif';
  (board?.teams ?? ['', '']).forEach((name, k) => g.fillText(name.toUpperCase(), 120 + 360 * k, 52, 220));
  g.fillStyle = '#ff3b30';
  g.font = 'bold 120px ui-monospace, monospace';
  (board?.score ?? ['--', '--']).forEach((points, k) => g.fillText(String(points), 120 + 360 * k, 176));
  g.fillStyle = '#ffc531';
  g.font = 'bold 44px ui-monospace, monospace';
  g.fillText((board?.set ?? '').toUpperCase(), 300, 140, 120);
}

/** A net's mesh: 10 cm squares of dark cord, see-through between. */
const netMesh = () => {
  const texture = painted(32, 32, (g) => {
    g.strokeStyle = 'rgba(20, 20, 20, 0.85)';
    g.lineWidth = 3;
    g.strokeRect(0, 0, 32, 32);
  });
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(95, 9);
  return texture;
};

/** An antenna's red and white stripes, 10 cm each. */
const stripes = () => {
  const texture = painted(4, 32, (g) => {
    g.fillStyle = '#ffffff';
    g.fillRect(0, 0, 4, 32);
    g.fillStyle = '#d32f2f';
    g.fillRect(0, 0, 4, 16);
  });
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(1, 9);
  return texture;
};

/** A jersey number painted on a transparent square, for the front and back of a shirt. */
function shirtNumber(text: string, color: string): THREE.MeshBasicMaterial {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 128;
  const g = canvas.getContext('2d')!;
  g.fillStyle = color;
  g.font = 'bold 92px system-ui, sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(text, 64, 70);
  return new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true });
}

/** Text on a rounded sprite facing the camera, the same size on screen at any distance (scaled by
 * the caller), standing on its position. */
function tag(text: string, background: string, color: string): THREE.Sprite {
  const canvas = document.createElement('canvas');
  const g = canvas.getContext('2d')!;
  const font = '600 44px system-ui, sans-serif';
  g.font = font;
  canvas.width = Math.ceil(g.measureText(text).width) + 48;
  canvas.height = 72;
  g.fillStyle = background;
  g.beginPath();
  g.roundRect(0, 0, canvas.width, canvas.height, 18);
  g.fill();
  g.font = font;
  g.fillStyle = color;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(text, canvas.width / 2, canvas.height / 2 + 2);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false, sizeAttenuation: false }));
  sprite.center.set(0.5, 0);
  sprite.userData.aspect = canvas.width / canvas.height;
  sprite.renderOrder = 3;
  return sprite;
}

/** The scene in `element`: a court, its net, the players and the ball, turned with the pointer;
 * it draws only when something changes. */
export function mount(element: HTMLElement, sponsors: Sponsor[] = []): Scene {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  element.append(renderer.domElement);
  const scene = new THREE.Scene();
  // A depth range no wider than the scene: depth stays precise near the floor.
  const camera = new THREE.PerspectiveCamera(40, 1, 0.5, 80);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI / 2 - 0.05;
  controls.minDistance = 4;
  controls.maxDistance = 40;
  controls.target.copy(TARGET);
  // The nearest distance along EYE's direction framing FRAMED, found by halving.
  const frame3d = () => {
    const direction = new THREE.Vector3().subVectors(EYE, TARGET).normalize();
    let [near, far] = [controls.minDistance, controls.maxDistance];
    for (let k = 0; k < 24; k++) {
      const distance = (near + far) / 2;
      camera.position.copy(TARGET).addScaledVector(direction, distance);
      camera.lookAt(TARGET);
      camera.updateMatrixWorld();
      const fits = FRAMED.every((p) => {
        const q = p.clone().project(camera);
        return Math.abs(q.x) <= FIT && Math.abs(q.y) <= FIT;
      });
      [near, far] = fits ? [near, distance] : [distance, far];
    }
    camera.position.copy(TARGET).addScaledVector(direction, far);
    controls.update();
  };
  // Until the pointer turns the view, each new shape of it frames the court again.
  let turned = false;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x888888, 2.2));
  // The hall's lights, high above: the players, the referee and the net cast soft shadows on the floor.
  const sun = new THREE.DirectionalLight(0xffffff, 1.3);
  sun.position.set(-4, 16, 6);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -16, right: 16, top: 12, bottom: -12, near: 1, far: 40 });
  sun.shadow.normalBias = 0.02;
  sun.shadow.radius = 4;
  scene.add(sun);
  const castShadows = (object: THREE.Object3D) => object.traverse((o) => (o.castShadow = o instanceof THREE.Mesh));

  const solid = (color = 0xffffff) => new THREE.MeshLambertMaterial({ color });
  // The floor's layers (hall, court, lines, then shadows and rings) are drawn in that order without
  // writing depth, not told apart by millimetres of height: no flicker between them. A glossy blue
  // hall floor, the wooden court on it, both taking the shadows.
  const glossy = (geometry: THREE.PlaneGeometry, color: number, order: number, map?: THREE.Texture) => {
    const mesh = new THREE.Mesh(geometry, new THREE.MeshPhongMaterial({ color, map, specular: 0x3a3a3a, shininess: 70, depthWrite: false }));
    mesh.rotation.x = -Math.PI / 2;
    mesh.renderOrder = order;
    mesh.receiveShadow = true;
    return mesh;
  };
  scene.add(glossy(new THREE.PlaneGeometry(36, 28), 0x2f6db5, -3), glossy(new THREE.PlaneGeometry(18, 9), 0xffffff, -2, wood()));
  // The lines: the boundary, the centre line and the attack lines, 5 cm wide.
  const lines = new THREE.Group();
  const line = new THREE.MeshPhongMaterial({ color: 0xf6f6f6, specular: 0x666666, shininess: 90, depthWrite: false });
  const strip = (x: number, y: number, w: number, d: number) => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, d), line);
    mesh.rotation.x = -Math.PI / 2;
    mesh.renderOrder = -1;
    mesh.position.copy(at(x, y, 0));
    lines.add(mesh);
  };
  strip(0, -4.5, 18.05, 0.05);
  strip(0, 4.5, 18.05, 0.05);
  for (const x of [-9, -3, 0, 3, 9]) {
    strip(x, 0, 0.05, 9);
  }
  scene.add(lines);
  // The net: two posts in red pads, a see-through mesh, a white band on top.
  const post = solid(0x555555);
  const pad = solid(0xc0392b);
  for (const y of [-5, 5]) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, NET_TOP + 0.2, 12), post);
    mesh.position.copy(at(0, y, (NET_TOP + 0.2) / 2));
    const padding = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 1.9, 16), pad);
    padding.position.copy(at(0, y, 0.95));
    castShadows(mesh);
    castShadows(padding);
    scene.add(mesh, padding);
  }
  const net = new THREE.Mesh(new THREE.PlaneGeometry(9.5, 0.9), new THREE.MeshBasicMaterial({ map: netMesh(), transparent: true, side: THREE.DoubleSide, depthWrite: false }));
  net.rotation.y = Math.PI / 2;
  net.position.copy(at(0, 0, NET_TOP - 0.5));
  scene.add(net);
  // White bands along its top and bottom; an antenna over each sideline.
  for (const [h, high] of [
    [NET_TOP - 0.035, 0.07],
    [NET_TOP - 0.98, 0.05],
  ]) {
    const band = new THREE.Mesh(new THREE.BoxGeometry(0.02, high, 9.6), solid());
    band.position.copy(at(0, 0, h));
    castShadows(band);
    scene.add(band);
  }
  const antenna = new THREE.MeshLambertMaterial({ map: stripes() });
  for (const y of [-4.5, 4.5]) {
    const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 1.8, 8), antenna);
    rod.position.copy(at(0, y, NET_TOP - 0.1));
    scene.add(rod);
  }

  // The hall's walls, seen only from inside: the one between the camera and the court is not drawn.
  // A blue band along the bottom, pale above, windows high up, a scoreboard and doors.
  const WALL = 7;
  const BAND = 2.4;
  // Lit from above, the walls glow a little to read as pale as a real hall's.
  const pale = new THREE.MeshLambertMaterial({ color: 0xe9ebee, emissive: 0x6b6d70 });
  const banded = new THREE.MeshLambertMaterial({ color: 0x2a5ea8, emissive: 0x122a4c });
  const panes = new THREE.MeshBasicMaterial({ map: windowPanes() });
  const doorMaterial = solid(0x23345c);
  const exit = new THREE.MeshBasicMaterial({ color: 0x2ecc71 });
  const wall = (length: number, x: number, y: number, turn: number, windows: number[], doors: number[]) => {
    const side = new THREE.Group();
    const face = (height: number, h: number, material: THREE.Material) => {
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(length, height), material);
      mesh.position.set(0, h, 0);
      side.add(mesh);
    };
    face(BAND, BAND / 2, banded);
    face(WALL - BAND, (WALL + BAND) / 2, pale);
    for (const along of windows) {
      const pane = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.4), panes);
      pane.position.set(along, 5.5, 0.02);
      side.add(pane);
    }
    for (const along of doors) {
      const door = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 2.2), doorMaterial);
      door.position.set(along, 1.1, 0.02);
      const sign = new THREE.Mesh(new THREE.PlaneGeometry(0.4, 0.15), exit);
      sign.position.set(along, 2.5, 0.02);
      side.add(door, sign);
    }
    side.position.copy(at(x, y));
    side.rotation.y = turn;
    scene.add(side);
    return side;
  };
  const far = wall(36, 0, -14, 0, [-14, -9, 9, 14], []);
  // The scoreboard, repainted when the score changes.
  const boardTexture = painted(600, 280, (g) => paintScoreboard(g.canvas, null));
  let shown = '';
  const board = new THREE.Mesh(new THREE.PlaneGeometry(3, 1.4), new THREE.MeshBasicMaterial({ map: boardTexture }));
  board.position.set(0, 4.4, 0.03);
  far.add(board);
  wall(36, 0, 14, Math.PI, [-9, 9], []);
  wall(28, -18, 0, Math.PI / 2, [-6, 6], [-9, 9]);
  wall(28, 18, 0, -Math.PI / 2, [-6, 6], [-9, 9]);
  // Advertising boards along the front of the stands, 3 m each: the sponsors in turn, a blank one
  // between two of them.
  const PANEL = 3;
  const boards = sponsors.map((sponsor) => {
    const texture = painted(600, 160, () => {});
    const paint = (picture?: HTMLImageElement) => {
      const g = (texture.image as HTMLCanvasElement).getContext('2d')!;
      g.fillStyle = sponsor.background;
      g.fillRect(0, 0, 600, 160);
      // A logo alone fills the board's height, centred; a picture otherwise stands at both ends of the name.
      if (!sponsor.text) {
        if (picture) {
          const width = Math.min(580, (picture.width * 150) / picture.height);
          g.drawImage(picture, 300 - width / 2, 80 - (width * picture.height) / picture.width / 2, width, (width * picture.height) / picture.width);
        }
        texture.needsUpdate = true;
        return;
      }
      const width = picture ? (picture.width * 140) / picture.height : 0;
      for (const x of picture ? [20, 580 - width] : []) {
        g.drawImage(picture!, x, 10, width, 140);
      }
      g.fillStyle = sponsor.text;
      g.font = 'bold 96px system-ui, sans-serif';
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.fillText(sponsor.name, 300, 86, 600 - 2 * (width + 40));
      texture.needsUpdate = true;
    };
    paint();
    if (sponsor.logo) {
      const picture = new Image();
      picture.onload = () => {
        paint(picture);
        request();
      };
      picture.src = sponsor.logo;
    }
    return new THREE.MeshBasicMaterial({ map: texture });
  });
  const blank = new THREE.MeshBasicMaterial({ color: 0xf2f2f2 });
  if (boards.length) {
    for (let n = 0; n < 24 / PANEL; n++) {
      const board = new THREE.Mesh(new THREE.PlaneGeometry(PANEL - 0.04, 0.8), n % 2 ? blank : boards[(n / 2) % boards.length]);
      board.position.copy(at(-12 + PANEL / 2 + n * PANEL, -9.75, 0.42));
      scene.add(board);
    }
  }

  // Players: chibi figures about 1.65 m tall facing +z, shirt and shorts in their team's colours, a
  // soft shadow and their number above them; made as they first show.
  const shadow = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.18, depthWrite: false });
  const disc = new THREE.CircleGeometry(1, 24);
  const bodies = new Map<number, { group: THREE.Group; shadow: THREE.Mesh; label: string; team: number }>();
  const teamMaterials = [solid(), solid()];
  const shortsMaterials = [solid(), solid()];
  const skin = solid(SKIN);
  const white = solid(0xf2f2f2);
  const pads = solid(0x222222);
  const eye = solid(0x1c1410);
  const hairs = HAIRS.map((color) => solid(color));
  /** A figure in `shirt` and `shorts`; `seated` leaves out the legs, hidden by the seat. */
  const figure = (hair: number, shirt: THREE.Material, shorts: THREE.Material, seated = false) => {
    const group = new THREE.Group();
    const part = (geometry: THREE.BufferGeometry, material: THREE.Material, x: number, y: number, z = 0) => {
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(x, y, z);
      group.add(mesh);
      return mesh;
    };
    for (const side of [-1, 1]) {
      if (!seated) {
        part(new THREE.BoxGeometry(0.12, 0.08, 0.23), white, side * 0.1, 0.04, 0.03);
        part(new THREE.CylinderGeometry(0.06, 0.055, 0.22, 10), white, side * 0.1, 0.19);
        part(new THREE.CylinderGeometry(0.066, 0.06, 0.22, 10), skin, side * 0.1, 0.39);
        part(new THREE.CylinderGeometry(0.075, 0.075, 0.1, 10), pads, side * 0.1, 0.4);
      }
      part(new THREE.CapsuleGeometry(0.075, 0.1, 4, 10), shirt, side * 0.26, 1.0).rotation.z = side * 0.3;
      part(new THREE.CapsuleGeometry(0.055, 0.22, 4, 10), skin, side * 0.3, 0.78).rotation.z = side * 0.12;
      part(new THREE.SphereGeometry(0.03, 10, 8), eye, side * 0.085, 1.39, 0.235);
    }
    part(new THREE.CylinderGeometry(0.21, 0.22, 0.2, 18), shorts, 0, 0.58).scale.z = 0.75;
    part(new THREE.CylinderGeometry(0.24, 0.2, 0.42, 18), shirt, 0, 0.88).scale.z = 0.7;
    part(new THREE.SphereGeometry(0.24, 18, 10), shirt, 0, 1.08).scale.set(1, 0.42, 0.7);
    part(new THREE.CylinderGeometry(0.06, 0.06, 0.1, 10), skin, 0, 1.15);
    part(new THREE.SphereGeometry(0.25, 24, 18), skin, 0, 1.38);
    // A cap of hair over the top, tilted back to leave the forehead bare.
    part(new THREE.SphereGeometry(0.265, 24, 14, 0, Math.PI * 2, 0, Math.PI * 0.55), hairs[Math.abs(hair) % hairs.length], 0, 1.4).rotation.x = -0.35;
    return group;
  };
  // The first referee on a stand behind the far post, facing the court.
  const black = solid(0x202020);
  const stand = new THREE.Mesh(new THREE.BoxGeometry(0.6, 1.0, 0.6), solid(0xa7afb8));
  stand.position.copy(at(0, -5.8, 0.5));
  const referee = figure(3, black, black);
  referee.position.copy(at(0, -5.8, 1.0));
  castShadows(stand);
  castShadows(referee);
  scene.add(stand, referee);
  // Stands along the far side: three pale tiers with blue seats, spectators seated with gaps between groups.
  const tier = solid(0xd3d7dc);
  const seat = solid(0x2c5fa8);
  const shirts = CROWD.map((color) => solid(color));
  for (let row = 0; row < 3; row++) {
    const top = 0.45 * (row + 1);
    const depth = -10.2 - 0.8 * row;
    const bench = new THREE.Mesh(new THREE.BoxGeometry(24, top, 0.8), tier);
    bench.position.copy(at(0, depth, top / 2));
    const seats = new THREE.Mesh(new THREE.BoxGeometry(24, 0.08, 0.4), seat);
    seats.position.copy(at(0, depth + 0.15, top + 0.04));
    scene.add(bench, seats);
    for (let k = 0; k < 22; k++) {
      const n = row * 22 + k;
      if ((n * 5) % 7 < 3) {
        continue;
      }
      const fan = figure(n, shirts[(n * 7 + 3) % shirts.length], black, true);
      fan.position.copy(at(-11 + k + 0.4 * (row % 2), depth, top - 0.5));
      scene.add(fan);
    }
  }
  const player = (key: number, team: number, label: string, colors: SceneState['colors']) => {
    const known = bodies.get(key);
    if (known && known.label === label && known.team === team) {
      return known;
    }
    if (known) {
      scene.remove(known.group, known.shadow);
    }
    const group = figure(key, teamMaterials[team - 1], shortsMaterials[team - 1]);
    const numbers = shirtNumber(label, colors.teamText[team - 1]);
    const plane = new THREE.PlaneGeometry(0.22, 0.22);
    for (const side of [1, -1]) {
      const mesh = new THREE.Mesh(plane, numbers);
      mesh.position.set(0, 0.9, side * 0.158);
      mesh.rotation.y = side === 1 ? 0 : Math.PI;
      group.add(mesh);
    }
    const number = badge(label, colors.team[team - 1], colors.teamText[team - 1]);
    number.position.y = 2.0;
    group.add(number);
    group.userData.key = key;
    castShadows(group);
    const ground = new THREE.Mesh(disc, shadow);
    ground.rotation.x = -Math.PI / 2;
    ground.scale.setScalar(0.32);
    scene.add(group, ground);
    const made = { group, shadow: ground, label, team };
    bodies.set(key, made);
    return made;
  };

  // A match ball's yellow: it stands out from the floor and both teams.
  const ballMaterial = new THREE.MeshLambertMaterial({ color: 0xf5c518, emissive: 0x3a2a00 });
  const ball = new THREE.Mesh(new THREE.SphereGeometry(BALL_R, 24, 16), ballMaterial);
  const ballShadow = new THREE.Mesh(disc, shadow);
  ballShadow.rotation.x = -Math.PI / 2;
  ballShadow.scale.setScalar(BALL_R * 1.2);
  const trailMaterial = new THREE.MeshBasicMaterial({ transparent: true, vertexColors: true, depthWrite: false, side: THREE.DoubleSide });
  const trail = new THREE.Mesh(new THREE.BufferGeometry(), trailMaterial);
  ball.castShadow = true;
  scene.add(ball, ballShadow, trail);
  // Rings on the floor: around a player touching the ball, where it lands.
  const rings: THREE.Mesh[] = [];
  const ringMaterial = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide });
  const landingMaterial = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide });
  const ringGeometry = new THREE.RingGeometry(0.92, 1, 40);

  // The hovered player's name, above their number.
  let tip: { text: string; sprite: THREE.Sprite } | null = null;
  const raycaster = new THREE.Raycaster();

  let frame = 0;
  const draw = () => {
    frame = 0;
    controls.update();
    renderer.render(scene, camera);
    // Damping carries the turn on over the next frames.
    if (moving) {
      request();
    }
  };
  const request = () => {
    frame ||= requestAnimationFrame(draw);
  };
  let moving = false;
  controls.addEventListener('start', () => {
    moving = true;
    turned = true;
  });
  controls.addEventListener('end', () => {
    setTimeout(() => (moving = false), 600);
  });
  controls.addEventListener('change', request);
  const resize = () => {
    const { width, height } = element.getBoundingClientRect();
    const size = renderer.getSize(new THREE.Vector2());
    if (Math.round(width) === size.x && Math.round(height) === size.y) {
      return;
    }
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(1, height);
    camera.updateProjectionMatrix();
    if (!turned) {
      frame3d();
    }
    // Resizing clears the canvas: drawn at once, not a frame later, or it shows empty for a frame.
    renderer.render(scene, camera);
  };
  const observer = new ResizeObserver(resize);
  observer.observe(element);
  resize();

  return {
    update(state) {
      const { colors } = state;
      teamMaterials.forEach((m, k) => m.color.set(colors.team[k]));
      shortsMaterials.forEach((m, k) => m.color.set(colors.team[k]).multiplyScalar(0.78));
      ringMaterial.color.set(colors.foreground);
      landingMaterial.color.set(colors.primary);
      const seen = new Set<number>();
      for (const p of state.players) {
        const body = player(p.key, p.team, p.label, colors);
        body.group.position.copy(at(p.x, p.y, p.jump));
        // Facing the ball, else the net.
        const [tx, ty] = state.ball ? [state.ball.x, state.ball.y] : [0, p.y];
        if (Math.hypot(tx - p.x, ty - p.y) > 0.3) {
          body.group.rotation.y = Math.atan2(tx - p.x, ty - p.y);
        }
        body.shadow.position.copy(at(p.x, p.y, 0.006));
        body.group.visible = body.shadow.visible = true;
        seen.add(p.key);
      }
      for (const [key, body] of bodies) {
        if (!seen.has(key)) {
          body.group.visible = body.shadow.visible = false;
        }
      }
      if (JSON.stringify(state.board) !== shown) {
        shown = JSON.stringify(state.board);
        paintScoreboard(boardTexture.image as HTMLCanvasElement, state.board);
        boardTexture.needsUpdate = true;
      }
      const tipped = state.players.find((p) => p.tip);
      if (tip && tip.text !== tipped?.tip) {
        scene.remove(tip.sprite);
        tip.sprite.material.map?.dispose();
        tip.sprite.material.dispose();
        tip = null;
      }
      if (tipped?.tip) {
        tip ??= { text: tipped.tip, sprite: tag(tipped.tip, colors.foreground, colors.floor) };
        // Unattenuated sprites are sized as at 1 m from the camera.
        const height = (TIP_PX / Math.max(1, renderer.domElement.clientHeight)) * 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
        tip.sprite.scale.set(height * tip.sprite.userData.aspect, height, 1);
        tip.sprite.position.copy(at(tipped.x, tipped.y, tipped.jump + 2.4));
        scene.add(tip.sprite);
      }
      ball.visible = ballShadow.visible = state.ball !== null;
      if (state.ball) {
        ball.position.copy(at(state.ball.x, state.ball.y, Math.max(BALL_R, state.ball.h)));
        ballShadow.position.copy(at(state.ball.x, state.ball.y, 0.007));
      }
      // The trail: a ribbon facing the camera, from transparent at its tail to the ball, as wide and
      // strong as the ball is fast (a slow set leaves almost none, an attack a streak).
      const points = state.trail.map((p) => at(p.x, p.y, Math.max(BALL_R, p.h)));
      const length = points.slice(1).reduce((sum, p, k) => sum + p.distanceTo(points[k]), 0);
      const strength = Math.min(1, Math.max(0, (length / TRAIL_S - SLOW) / (FAST - SLOW)));
      trail.visible = points.length > 1 && strength > 0;
      if (trail.visible) {
        const vertices: number[] = [];
        const shades: number[] = [];
        const tint = new THREE.Color(colors.foreground);
        points.forEach((p, k) => {
          const next = points[Math.min(k + 1, points.length - 1)];
          const back = points[Math.max(k - 1, 0)];
          const along = (k + 1) / points.length;
          const side = new THREE.Vector3()
            .subVectors(next, back)
            .cross(new THREE.Vector3().subVectors(camera.position, p))
            .normalize()
            .multiplyScalar(BALL_R * (0.35 + 0.65 * strength) * along);
          vertices.push(p.x + side.x, p.y + side.y, p.z + side.z, p.x - side.x, p.y - side.y, p.z - side.z);
          const alpha = 0.6 * strength * along * along;
          shades.push(tint.r, tint.g, tint.b, alpha, tint.r, tint.g, tint.b, alpha);
        });
        const index: number[] = [];
        for (let k = 0; k < points.length - 1; k++) {
          index.push(2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 1, 2 * k + 3, 2 * k + 2);
        }
        trail.geometry.dispose();
        trail.geometry = new THREE.BufferGeometry()
          .setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
          .setAttribute('color', new THREE.Float32BufferAttribute(shades, 4))
          .setIndex(index);
      }
      const wanted = [...state.rings.map((r) => ({ ...r, landing: false })), ...state.landings.map((r) => ({ ...r, landing: true }))];
      while (rings.length < wanted.length) {
        const ring = new THREE.Mesh(ringGeometry, ringMaterial);
        ring.rotation.x = -Math.PI / 2;
        scene.add(ring);
        rings.push(ring);
      }
      rings.forEach((ring, k) => {
        const r = wanted[k];
        ring.visible = r !== undefined;
        if (r) {
          ring.material = r.landing ? landingMaterial : ringMaterial;
          ring.position.copy(at(r.x, r.y, 0.008));
          ring.scale.setScalar(r.landing ? 0.3 + 1.4 * r.f : 0.5 + 0.5 * r.f);
        }
      });
      // One opacity per material: the newest ring's.
      ringMaterial.opacity = 1 - (state.rings[0]?.f ?? 0);
      landingMaterial.opacity = 1 - (state.landings[0]?.f ?? 0);
      request();
    },
    pick(clientX, clientY) {
      const box = renderer.domElement.getBoundingClientRect();
      raycaster.setFromCamera(new THREE.Vector2(((clientX - box.left) / box.width) * 2 - 1, 1 - ((clientY - box.top) / box.height) * 2), camera);
      const shown = [...bodies.values()].filter((b) => b.group.visible).map((b) => b.group);
      let hit: THREE.Object3D | null = raycaster.intersectObjects(shown, true)[0]?.object ?? null;
      while (hit && hit.userData.key === undefined) {
        hit = hit.parent;
      }
      return hit ? (hit.userData.key as number) : null;
    },
    dispose() {
      observer.disconnect();
      cancelAnimationFrame(frame);
      controls.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}
