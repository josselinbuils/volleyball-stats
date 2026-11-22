/// <reference types="webxr" />
// The page's loops ask their next frame here: from the window, or from the headset while the 3D view is in VR, where a
// browser may hold the window's frames back.
let session: XRSession | null = null;
const waiting = new Set<(time: number) => void>();

/** Runs `callback` at the next frame; returns what cancels it. */
export function nextFrame(callback: (time: number) => void): () => void {
  let done = false;
  const run = (time: number) => {
    if (!done) {
      done = true;
      waiting.delete(run);
      callback(time);
    }
  };
  waiting.add(run);
  ask(run);
  return () => {
    done = true;
    waiting.delete(run);
  };
}

const ask = (run: (time: number) => void) => (session ? session.requestAnimationFrame((time) => run(time)) : requestAnimationFrame(run));

/** The headset's session the frames come from, null for the window's; the frames already asked are asked again there. */
export function frameSource(next: XRSession | null): void {
  session = next;
  waiting.forEach(ask);
}
