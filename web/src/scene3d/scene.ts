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

export type View = 'stand' | 'server' | 'top';

export interface Scene {
  update: (state: SceneState) => void;
  view: (name: View) => void;
  dispose: () => void;
}

// Camera positions and the point they look at: from the stand behind the camera's sideline, a little
// to the left so the net shows in perspective; behind the left end line; from above.
const VIEWS: Record<View, [THREE.Vector3, THREE.Vector3]> = {
  stand: [new THREE.Vector3(-3.5, 7.5, 15.5), new THREE.Vector3(0.5, 0.6, 0)],
  server: [new THREE.Vector3(-16, 3.4, 0), new THREE.Vector3(3, 1, 0)],
  top: [new THREE.Vector3(0, 21, 0.01), new THREE.Vector3(0, 0, 0)],
};
const NET_TOP = 2.35;
const BALL_R = 0.11;

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
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI / 2 - 0.05;
  controls.minDistance = 4;
  controls.maxDistance = 40;
  camera.position.copy(VIEWS.stand[0]);
  controls.target.copy(VIEWS.stand[1]);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x888888, 2.2));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2);
  sun.position.set(-6, 14, 8);
  scene.add(sun);

  const solid = (color = 0xffffff) => new THREE.MeshLambertMaterial({ color });
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(30, 18), solid());
  floor.rotation.x = -Math.PI / 2;
  const court = new THREE.Mesh(new THREE.PlaneGeometry(18, 9), solid());
  court.rotation.x = -Math.PI / 2;
  court.position.y = 0.002;
  scene.add(floor, court);
  // The lines: the boundary, the centre line and the attack lines, 5 cm wide.
  const lines = new THREE.Group();
  const line = solid();
  const strip = (x: number, y: number, w: number, d: number) => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, d), line);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.copy(at(x, y, 0.004));
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

  const ballMaterial = new THREE.MeshLambertMaterial({ color: 0xffffff });
  const ball = new THREE.Mesh(new THREE.SphereGeometry(BALL_R, 24, 16), ballMaterial);
  const ballShadow = new THREE.Mesh(disc, shadow);
  ballShadow.rotation.x = -Math.PI / 2;
  ballShadow.scale.setScalar(BALL_R * 1.2);
  const trailMaterial = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.35, depthWrite: false });
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
    // Damping and view changes carry on over the next frames.
    if (moving) {
      request();
    }
  };
  const request = () => {
    frame ||= requestAnimationFrame(draw);
  };
  let moving = false;
  let flight: { from: [THREE.Vector3, THREE.Vector3]; to: [THREE.Vector3, THREE.Vector3]; start: number } | null = null;
  controls.addEventListener('start', () => {
    moving = true;
    flight = null;
  });
  controls.addEventListener('end', () => {
    setTimeout(() => (moving = false), 600);
  });
  controls.addEventListener('change', request);
  const fly = () => {
    if (!flight) {
      return;
    }
    const f = Math.min(1, (performance.now() - flight.start) / 700);
    const ease = 1 - (1 - f) ** 3;
    camera.position.lerpVectors(flight.from[0], flight.to[0], ease);
    controls.target.lerpVectors(flight.from[1], flight.to[1], ease);
    renderer.render(scene, camera);
    if (f < 1) {
      requestAnimationFrame(fly);
    } else {
      flight = null;
    }
  };

  const resize = () => {
    const { width, height } = element.getBoundingClientRect();
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(1, height);
    camera.updateProjectionMatrix();
    request();
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
      trailMaterial.color.set(colors.foreground);
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
      // The trail: a ribbon facing up, widening towards the ball.
      const points = state.trail.map((p) => at(p.x, p.y, Math.max(BALL_R, p.h)));
      trail.visible = points.length > 1;
      if (trail.visible) {
        const vertices: number[] = [];
        points.forEach((p, k) => {
          const next = points[Math.min(k + 1, points.length - 1)];
          const back = points[Math.max(k - 1, 0)];
          const side = new THREE.Vector3()
            .subVectors(next, back)
            .cross(new THREE.Vector3(0, 1, 0))
            .normalize()
            .multiplyScalar((BALL_R * (k + 1)) / points.length);
          vertices.push(p.x + side.x, p.y + side.y, p.z + side.z, p.x - side.x, p.y - side.y, p.z - side.z);
        });
        const index: number[] = [];
        for (let k = 0; k < points.length - 1; k++) {
          index.push(2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 1, 2 * k + 3, 2 * k + 2);
        }
        trail.geometry.dispose();
        trail.geometry = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)).setIndex(index);
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
    view(name) {
      flight = { from: [camera.position.clone(), controls.target.clone()], to: VIEWS[name], start: performance.now() };
      requestAnimationFrame(fly);
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
