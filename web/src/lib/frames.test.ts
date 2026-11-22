import { afterEach, describe, expect, it, vi } from 'vitest';
import { frameSource, nextFrame } from '@/lib/frames';

/** A frame source whose frames run when `flush` is called. */
const source = () => {
  let queued: ((time: number) => void)[] = [];
  return {
    ask: (run: (time: number) => void) => queued.push(run),
    flush: () => {
      const runs = queued;
      queued = [];
      runs.forEach((run) => run(0));
    },
  };
};

describe('nextFrame', () => {
  afterEach(() => {
    frameSource(null);
    vi.unstubAllGlobals();
  });

  it('moves a waiting frame to the headset and back, running it once', () => {
    const page = source();
    const headset = source();
    vi.stubGlobal('requestAnimationFrame', page.ask);
    const runs: string[] = [];
    nextFrame(() => runs.push('a'));
    // The window holds its frames back in VR: the headset's run it.
    frameSource({ requestAnimationFrame: headset.ask } as unknown as XRSession);
    headset.flush();
    page.flush();
    expect(runs).toEqual(['a']);
    // A loop asked during the session keeps running after it ends: the window takes its frame.
    nextFrame(() => runs.push('b'));
    frameSource(null);
    page.flush();
    headset.flush();
    expect(runs).toEqual(['a', 'b']);
  });

  it('cancels', () => {
    const page = source();
    vi.stubGlobal('requestAnimationFrame', page.ask);
    const runs: string[] = [];
    nextFrame(() => runs.push('a'))();
    page.flush();
    expect(runs).toEqual([]);
  });
});
