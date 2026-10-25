import { describe, expect, it, vi } from 'vitest';
import { Clock } from '@/lib/clock';

describe('Clock', () => {
  it('runs at its rate while playing, stops at the end, and seeks within the duration', () => {
    // Frames every 16 ms of fake time, the test environment having none.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
    vi.stubGlobal('requestAnimationFrame', (run: FrameRequestCallback) => setTimeout(() => run(performance.now()), 16));
    vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
    const clock = new Clock({} as HTMLElement, 10);
    const events: string[] = [];
    ['play', 'pause', 'seeked'].forEach((name) => clock.addEventListener(name, () => events.push(name)));

    clock.currentTime = 4;
    void clock.play();
    vi.advanceTimersByTime(1000);
    expect(clock.currentTime).toBeCloseTo(5, 1);

    clock.playbackRate = 0.5;
    vi.advanceTimersByTime(2000);
    expect(clock.currentTime).toBeCloseTo(6, 1);

    clock.currentTime = 99;
    expect(clock.currentTime).toBe(10);
    vi.advanceTimersByTime(100);
    expect(clock.paused).toBe(true);
    expect(events).toEqual(['seeked', 'play', 'seeked', 'pause']);
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
});
