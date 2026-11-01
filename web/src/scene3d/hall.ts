import * as THREE from 'three';
import type { Sponsor } from '@/lib/match';

// The first match's gym, measured through its camera (court metres, net at x = 0, the camera's side y > 0): a handball
// court across the volleyball court, a timber roof, a stand on the x > 0 side.
const WALL_X = 13.8;
const FAR_Y = -32.5;
const NEAR_Y = 15;
const GREY_TOP = 3.1;
const EAVES = 7.6;
const RIDGE = 12;
const HANDBALL = { x: 10, near: 11.7, far: -28.3, goal: 1.5, area: 6, free: 9 };
const STAND = { from: -30, to: 8, back: 19.2, rows: 7, top: 7 };
const MUSTARD = '#c8a212';
const MAGENTA = '#d8215a';
const GREY = 0x8a8274;
const PALE = 0xe6e0d2;
const TIMBER = 0x3a2a1b;
const CEILING = '#7a5a3e';
const DARK = 0x35342e;
const FLAGS = [0x233a8c, 0xf2c200];
// Floor pixels per metre.
const FLOOR_PX = 40;
// Sponsors' banners on the grey walls, under the bunting and well apart: their pictures' shape, where they hang, how wide.
const BANNER_RATIO = 600 / 160;
const SIDE_BANNER = 3;
const SIDE_BANNER_H = 1.7;
const SIDE_BANNERS = [-14, -5, 4];
const FAR_BANNER = { x: -7.5, h: 2, width: 4 };

/** A point in court metres to the scene's axes: x, height up, y towards the viewer. */
export const at = (x: number, y: number, h = 0) => new THREE.Vector3(x, h, y);

/** A canvas of `width` × `height` pixels drawn by `paint`, as a texture. */
export function painted(width: number, height: number, paint: (g: CanvasRenderingContext2D) => void): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  paint(canvas.getContext('2d')!);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** The hall's floor: its magenta surround, the mustard handball court, its goal areas and lines, the centre disc. */
function floorTexture(maxAnisotropy: number): THREE.CanvasTexture {
  const width = 2 * WALL_X;
  const depth = NEAR_Y - FAR_Y;
  const texture = painted(Math.round(width * FLOOR_PX), Math.round(depth * FLOOR_PX), (g) => {
    const px = (x: number) => (x + WALL_X) * FLOOR_PX;
    const py = (y: number) => (y - FAR_Y) * FLOOR_PX;
    g.fillStyle = MAGENTA;
    g.fillRect(0, 0, g.canvas.width, g.canvas.height);
    g.fillStyle = MUSTARD;
    g.fillRect(px(-HANDBALL.x), py(HANDBALL.far), 2 * HANDBALL.x * FLOOR_PX, (HANDBALL.near - HANDBALL.far) * FLOOR_PX);
    // A goal's area: two quarter circles around its posts joined by a straight line, `sign` towards the court.
    const area = (line: number, sign: number, radius: number) => {
      g.beginPath();
      g.arc(px(-HANDBALL.goal), py(line), radius * FLOOR_PX, sign > 0 ? Math.PI : -Math.PI, sign > 0 ? Math.PI / 2 : -Math.PI / 2, sign > 0);
      g.arc(px(HANDBALL.goal), py(line), radius * FLOOR_PX, sign > 0 ? Math.PI / 2 : -Math.PI / 2, 0, sign > 0);
    };
    for (const [line, sign] of [
      [HANDBALL.near, -1],
      [HANDBALL.far, 1],
    ]) {
      area(line, sign, HANDBALL.area);
      g.closePath();
      g.fillStyle = MAGENTA;
      g.fill();
      g.strokeStyle = '#f7f4ec';
      g.lineWidth = 3;
      g.stroke();
      area(line, sign, HANDBALL.free);
      g.setLineDash([24, 24]);
      g.stroke();
      g.setLineDash([]);
    }
    g.strokeStyle = '#f7f4ec';
    g.lineWidth = 3;
    g.strokeRect(px(-HANDBALL.x), py(HANDBALL.far), 2 * HANDBALL.x * FLOOR_PX, (HANDBALL.near - HANDBALL.far) * FLOOR_PX);
    // The centre disc of the hall, and a basketball arc each side.
    const middle = (HANDBALL.near + HANDBALL.far) / 2;
    g.fillStyle = '#23262b';
    g.beginPath();
    g.arc(px(0), py(middle), 1.8 * FLOOR_PX, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = '#efcf2c';
    g.lineWidth = 3;
    for (const sign of [-1, 1]) {
      g.beginPath();
      g.arc(px(sign * 12.4), py(middle), 6.75 * FLOOR_PX, 0, Math.PI * 2);
      g.stroke();
    }
    g.strokeStyle = '#f7f4ec';
    g.beginPath();
    g.moveTo(px(-HANDBALL.x), py(middle));
    g.lineTo(px(HANDBALL.x), py(middle));
    g.stroke();
  });
  texture.anisotropy = maxAnisotropy;
  return texture;
}

/** The far wall's black mural: broad strokes, always the same. */
const mural = () =>
  painted(1024, 512, (g) => {
    let seed = 11;
    const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
    g.lineCap = 'round';
    g.strokeStyle = '#141414';
    for (let k = 0; k < 90; k++) {
      g.lineWidth = 8 + random() * 34;
      g.beginPath();
      const x = random() * 1024;
      const y = random() * 512;
      g.moveTo(x, y);
      g.quadraticCurveTo(x + (random() - 0.5) * 320, y + (random() - 0.5) * 320, x + (random() - 0.5) * 420, y + (random() - 0.5) * 300);
      g.stroke();
    }
  });

/** The roof's panels between the beams. */
function ceiling(): THREE.CanvasTexture {
  const texture = painted(256, 256, (g) => {
    g.fillStyle = CEILING;
    g.fillRect(0, 0, 256, 256);
    g.fillStyle = 'rgba(30, 18, 8, 0.75)';
    g.fillRect(0, 0, 256, 7);
    g.fillRect(0, 0, 7, 256);
  });
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  return texture;
}

/** A flat four-cornered face seen only from the `inside` point's side. */
function face(corners: THREE.Vector3[], material: THREE.Material, inside: THREE.Vector3, uv?: number[]): THREE.Mesh {
  const geometry = new THREE.BufferGeometry().setFromPoints(corners);
  const normal = new THREE.Vector3().subVectors(corners[1], corners[0]).cross(new THREE.Vector3().subVectors(corners[2], corners[0]));
  const facing = normal.dot(new THREE.Vector3().subVectors(inside, corners[0])) > 0;
  geometry.setIndex(facing ? [0, 1, 2, 0, 2, 3] : [0, 2, 1, 0, 3, 2]);
  if (uv) {
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  }
  geometry.computeVertexNormals();
  return new THREE.Mesh(geometry, material);
}

/** Adds the gym to `scene`, the scoreboard showing `board`; `request` asks for a new drawing once a logo has loaded.
 * It returns the roof's frame, and what stops those logos. */
export function addHall(scene: THREE.Scene, sponsors: Sponsor[], board: THREE.Texture, maxAnisotropy: number, request: () => void): { frame: THREE.Group; stop: () => void } {
  const hall = new THREE.Group();
  scene.add(hall);
  const inside = at(0, -8, 3);
  const flat = (color: number) => new THREE.MeshLambertMaterial({ color, emissive: new THREE.Color(color).multiplyScalar(0.45) });
  const grey = flat(GREY);
  const pale = flat(PALE);
  const dark = new THREE.MeshBasicMaterial({ color: DARK });
  // The floor is drawn first without writing depth, the lines and shadows over it.
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(2 * WALL_X, NEAR_Y - FAR_Y),
    new THREE.MeshPhongMaterial({ map: floorTexture(maxAnisotropy), specular: 0x3a3a3a, shininess: 60, depthWrite: false }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.copy(at(0, (NEAR_Y + FAR_Y) / 2, 0));
  floor.renderOrder = -3;
  floor.receiveShadow = true;
  hall.add(floor);
  // A wall: its grey band and pale top from `a` to `b`, its `top` the height it goes up to.
  const wall = (a: [number, number], b: [number, number], from: number, to: number, material: THREE.Material) => {
    hall.add(face([at(a[0], a[1], from), at(b[0], b[1], from), at(b[0], b[1], to), at(a[0], a[1], to)], material, inside));
  };
  const corners = {
    farLeft: [-WALL_X, FAR_Y],
    farRight: [WALL_X, FAR_Y],
    nearLeft: [-WALL_X, NEAR_Y],
    nearRight: [WALL_X, NEAR_Y],
  } as const;
  const sides = [
    [corners.farLeft, corners.farRight],
    [corners.farLeft, corners.nearLeft],
    [corners.nearLeft, corners.nearRight],
    [corners.farRight, corners.nearRight],
  ] as const;
  for (const [a, b] of sides) {
    wall([a[0], a[1]], [b[0], b[1]], 0, GREY_TOP, grey);
  }
  wall([corners.farLeft[0], corners.farLeft[1]], [corners.farRight[0], corners.farRight[1]], GREY_TOP, EAVES, pale);
  wall([corners.farLeft[0], corners.farLeft[1]], [corners.nearLeft[0], corners.nearLeft[1]], GREY_TOP, EAVES, pale);
  wall([corners.nearLeft[0], corners.nearLeft[1]], [corners.nearRight[0], corners.nearRight[1]], GREY_TOP, EAVES, pale);
  // The x > 0 side stays open above the grey wall where the stand is.
  wall([WALL_X, FAR_Y], [WALL_X, STAND.from], GREY_TOP, EAVES, pale);
  wall([WALL_X, STAND.to], [WALL_X, NEAR_Y], GREY_TOP, EAVES, pale);
  // The stand: dark tiers going up and back, a wall behind them, closed above and at its ends.
  const standLength = STAND.to - STAND.from;
  for (let row = 0; row < STAND.rows; row++) {
    const depth = (STAND.back - WALL_X) / STAND.rows;
    const top = GREY_TOP + ((STAND.top - GREY_TOP) * (row + 1)) / STAND.rows;
    const step = new THREE.Mesh(new THREE.BoxGeometry(depth, top - GREY_TOP + 0.1, standLength), new THREE.MeshLambertMaterial({ color: row % 2 ? 0x45443c : 0x3c3b34 }));
    step.position.copy(at(WALL_X + depth * (row + 0.5), (STAND.from + STAND.to) / 2, (top + GREY_TOP) / 2 - 0.05));
    hall.add(step);
  }
  const standInside = at(WALL_X + 1, (STAND.from + STAND.to) / 2, 6);
  hall.add(face([at(STAND.back, STAND.from, GREY_TOP), at(STAND.back, STAND.to, GREY_TOP), at(STAND.back, STAND.to, RIDGE), at(STAND.back, STAND.from, RIDGE)], dark, standInside));
  for (const y of [STAND.from, STAND.to]) {
    hall.add(face([at(WALL_X, y, GREY_TOP), at(STAND.back, y, GREY_TOP), at(STAND.back, y, EAVES), at(WALL_X, y, EAVES)], dark, standInside));
  }
  hall.add(face([at(WALL_X, STAND.from, EAVES), at(STAND.back, STAND.from, EAVES), at(STAND.back, STAND.to, EAVES), at(WALL_X, STAND.to, EAVES)], dark, standInside));
  // The roof: a ridge along the hall over its panels, a timber frame every 6 m, two rows of lights.
  const panels = new THREE.MeshBasicMaterial({ map: ceiling() });
  const length = NEAR_Y - FAR_Y;
  const across = Math.hypot(WALL_X, RIDGE - EAVES);
  const uv = [0, 0, 0, length / 3, across / 3, length / 3, across / 3, 0];
  for (const side of [-1, 1]) {
    hall.add(face([at(side * WALL_X, FAR_Y, EAVES), at(side * WALL_X, NEAR_Y, EAVES), at(0, NEAR_Y, RIDGE), at(0, FAR_Y, RIDGE)], panels, inside, uv));
  }
  for (const y of [FAR_Y, NEAR_Y]) {
    const gable = new THREE.BufferGeometry().setFromPoints([at(-WALL_X, y, EAVES), at(WALL_X, y, EAVES), at(0, y, RIDGE)]);
    gable.setIndex(y === FAR_Y ? [0, 1, 2] : [0, 2, 1]);
    gable.computeVertexNormals();
    hall.add(new THREE.Mesh(gable, panels));
  }
  const timber = new THREE.MeshBasicMaterial({ color: TIMBER });
  const slope = Math.atan2(RIDGE - EAVES, WALL_X);
  const rafter = new THREE.BoxGeometry(across, 0.42, 0.28);
  const tie = new THREE.BoxGeometry(2 * WALL_X, 0.3, 0.24);
  const post = new THREE.BoxGeometry(0.22, RIDGE - EAVES, 0.22);
  const led = new THREE.CircleGeometry(0.22, 12);
  const lit = new THREE.MeshBasicMaterial({ color: 0xfff6dc });
  // Inside the hall only: from a camera above the roof they would cross the picture.
  const frame = new THREE.Group();
  hall.add(frame);
  for (let y = FAR_Y + 2.5; y < NEAR_Y; y += 6) {
    for (const side of [-1, 1]) {
      const beam = new THREE.Mesh(rafter, timber);
      beam.position.copy(at((side * WALL_X) / 2, y, (EAVES + RIDGE) / 2 - 0.3));
      beam.rotation.z = -side * slope;
      frame.add(beam);
      const light = new THREE.Mesh(led, lit);
      light.position.copy(at(side * 5.5, y + 3, RIDGE - (5.5 / WALL_X) * (RIDGE - EAVES) - 0.45));
      light.rotation.x = Math.PI / 2;
      frame.add(light);
      const brace = new THREE.Mesh(post, timber);
      brace.position.copy(at(side * 6.9, y, (EAVES + RIDGE) / 2 - 1));
      frame.add(brace);
    }
    const beam = new THREE.Mesh(tie, timber);
    beam.position.copy(at(0, y, EAVES + 0.2));
    frame.add(beam);
  }
  // The far wall: its goal, its mural, the scoreboard.
  const goal = new THREE.MeshLambertMaterial({ color: 0xf1ede3 });
  const bar = new THREE.BoxGeometry(0.08, 2, 0.08);
  for (const x of [-HANDBALL.goal, HANDBALL.goal]) {
    const mesh = new THREE.Mesh(bar, goal);
    mesh.position.copy(at(x, HANDBALL.far, 1));
    hall.add(mesh);
  }
  const crossbar = new THREE.Mesh(new THREE.BoxGeometry(2 * HANDBALL.goal + 0.08, 0.08, 0.08), goal);
  crossbar.position.copy(at(0, HANDBALL.far, 2));
  hall.add(crossbar);
  const onFar = (x: number, h: number, w: number, tall: number, material: THREE.Material) => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, tall), material);
    mesh.position.copy(at(x, FAR_Y + 0.02, h));
    hall.add(mesh);
  };
  onFar(4, 1.7, 7, 2.6, new THREE.MeshBasicMaterial({ map: mural(), transparent: true }));
  onFar(0, 5.3, 6, 2.8, new THREE.MeshBasicMaterial({ map: board }));
  onFar(-0.6, 2.5, 2.2, 0.8, new THREE.MeshBasicMaterial({ color: 0x1d1d1d }));
  // Bunting along the wall under the stand, blue and yellow.
  const pennant = new THREE.Shape();
  pennant.moveTo(-0.22, 0);
  pennant.lineTo(0.22, 0);
  pennant.lineTo(0, -0.48);
  const flags = Math.floor((STAND.to - STAND.from) / 1.1);
  const bunting = new THREE.InstancedMesh(new THREE.ShapeGeometry(pennant), new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }), flags);
  const placed = new THREE.Object3D();
  for (let k = 0; k < flags; k++) {
    const y = STAND.from + 0.5 + k * 1.1;
    placed.position.copy(at(WALL_X - 0.04, y, 2.95 - 0.12 * Math.abs(Math.sin(k * 0.7))));
    placed.rotation.y = -Math.PI / 2;
    placed.updateMatrix();
    bunting.setMatrixAt(k, placed.matrix);
    bunting.setColorAt(k, new THREE.Color(FLAGS[k % FLAGS.length]));
  }
  hall.add(bunting);
  // Sponsors' banners flat on the grey walls, as the hall's own adverts hang: on the far wall, and the sponsors in turn beside the court.
  let gone = false;
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
        if (gone) {
          return;
        }
        paint(picture);
        request();
      };
      picture.src = sponsor.logo;
    }
    return new THREE.MeshBasicMaterial({ map: texture });
  });
  if (boards.length) {
    onFar(FAR_BANNER.x, FAR_BANNER.h, FAR_BANNER.width, FAR_BANNER.width / BANNER_RATIO, boards[0]);
    for (const side of [-1, 1]) {
      SIDE_BANNERS.forEach((y, n) => {
        const panel = new THREE.Mesh(new THREE.PlaneGeometry(SIDE_BANNER, SIDE_BANNER / BANNER_RATIO), boards[n % boards.length]);
        panel.position.copy(at(side * (WALL_X - 0.03), y, SIDE_BANNER_H));
        panel.rotation.y = -side * (Math.PI / 2);
        hall.add(panel);
      });
    }
  }
  return {
    frame,
    stop: () => {
      gone = true;
    },
  };
}
