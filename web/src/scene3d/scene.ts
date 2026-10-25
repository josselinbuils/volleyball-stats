import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

/** A point of the scene in court metres: x along the court (net at 0), y across it (towards the
 * camera positive), h above the floor. */
export interface Point3 {
  x: number;
  y: number;
  h: number;
}

/** What the scene shows at a moment. Colours are CSS colours. */
export interface SceneState {
  players: { key: number; x: number; y: number; jump: number; team: 1 | 2; label: string }[];
  ball: Point3 | null;
  trail: Point3[];
  rings: { x: number; y: number; f: number }[];
  landings: { x: number; y: number; f: number }[];
  colors: { team: [string, string]; teamText: [string, string]; court: string; floor: string; line: string; foreground: string; primary: string };
}

export interface Scene {
  update: (state: SceneState) => void;
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

/** The scene in `element`: a court, its net, the players and the ball, turned with the pointer;
 * it draws only when something changes. */
export function mount(element: HTMLElement): Scene {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
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
  const sun = new THREE.DirectionalLight(0xffffff, 1.2);
  sun.position.set(-6, 14, 8);
  scene.add(sun);

  const solid = (color = 0xffffff) => new THREE.MeshLambertMaterial({ color });
  // The floor's layers (floor, court, lines, then shadows and rings) are drawn in that order without
  // writing depth, not told apart by millimetres of height: no flicker between them.
  const layer = (order: number) => {
    const material = solid();
    material.depthWrite = false;
    return { material, order };
  };
  const floorLayer = layer(-3);
  const courtLayer = layer(-2);
  const lineLayer = layer(-1);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 18), floorLayer.material);
  floor.rotation.x = -Math.PI / 2;
  floor.renderOrder = floorLayer.order;
  const court = new THREE.Mesh(new THREE.PlaneGeometry(18, 9), courtLayer.material);
  court.rotation.x = -Math.PI / 2;
  court.renderOrder = courtLayer.order;
  scene.add(floor, court);
  // The lines: the boundary, the centre line and the attack lines, 5 cm wide.
  const lines = new THREE.Group();
  const line = lineLayer.material;
  const strip = (x: number, y: number, w: number, d: number) => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, d), line);
    mesh.rotation.x = -Math.PI / 2;
    mesh.renderOrder = lineLayer.order;
    mesh.position.copy(at(x, y, 0));
    lines.add(mesh);
  };
  strip(0, -4.5, 18.05, 0.05);
  strip(0, 4.5, 18.05, 0.05);
  for (const x of [-9, -3, 0, 3, 9]) {
    strip(x, 0, 0.05, 9);
  }
  scene.add(lines);
  // The net: two posts, a see-through mesh, a white band on top.
  const post = solid(0x555555);
  for (const y of [-5, 5]) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, NET_TOP + 0.2, 12), post);
    mesh.position.copy(at(0, y, (NET_TOP + 0.2) / 2));
    scene.add(mesh);
  }
  const net = new THREE.Mesh(new THREE.PlaneGeometry(10, 1), new THREE.MeshBasicMaterial({ color: 0x222222, transparent: true, opacity: 0.25, side: THREE.DoubleSide }));
  net.rotation.y = Math.PI / 2;
  net.position.copy(at(0, 0, NET_TOP - 0.5));
  const band = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.07, 10), solid());
  band.position.copy(at(0, 0, NET_TOP - 0.035));
  scene.add(net, band);

  // Players: a body, a head, a soft shadow and their number above them; made as they first show.
  const shadow = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.18, depthWrite: false });
  const disc = new THREE.CircleGeometry(1, 24);
  const bodies = new Map<number, { group: THREE.Group; shadow: THREE.Mesh; label: string; team: number }>();
  const teamMaterials = [solid(), solid()];
  const player = (key: number, team: number, label: string, colors: SceneState['colors']) => {
    const known = bodies.get(key);
    if (known && known.label === label && known.team === team) {
      return known;
    }
    if (known) {
      scene.remove(known.group, known.shadow);
    }
    const group = new THREE.Group();
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.22, 0.9, 4, 12), teamMaterials[team - 1]);
    body.position.y = 0.67;
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.15, 16, 12), teamMaterials[team - 1]);
    head.position.y = 1.52;
    const number = badge(label, colors.team[team - 1], colors.teamText[team - 1]);
    number.position.y = 2.05;
    group.add(body, head, number);
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
  scene.add(ball, ballShadow, trail);
  // Rings on the floor: around a player touching the ball, where it lands.
  const rings: THREE.Mesh[] = [];
  const ringMaterial = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide });
  const landingMaterial = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, side: THREE.DoubleSide });
  const ringGeometry = new THREE.RingGeometry(0.92, 1, 40);

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
      floor.material.color.set(colors.floor);
      court.material.color.set(colors.court);
      line.color.set(colors.line);
      teamMaterials.forEach((m, k) => m.color.set(colors.team[k]));
      ringMaterial.color.set(colors.foreground);
      landingMaterial.color.set(colors.primary);
      const seen = new Set<number>();
      for (const p of state.players) {
        const body = player(p.key, p.team, p.label, colors);
        body.group.position.copy(at(p.x, p.y, p.jump));
        body.shadow.position.copy(at(p.x, p.y, 0.006));
        body.group.visible = body.shadow.visible = true;
        seen.add(p.key);
      }
      for (const [key, body] of bodies) {
        if (!seen.has(key)) {
          body.group.visible = body.shadow.visible = false;
        }
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
    dispose() {
      observer.disconnect();
      cancelAnimationFrame(frame);
      controls.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}
