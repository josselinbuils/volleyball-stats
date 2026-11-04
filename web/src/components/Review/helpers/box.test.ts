import { describe, expect, it } from 'vitest';
import { autoView, boxAt, MAX_ZOOM, panView, viewAt, zoomView, wheelZoom } from '@/components/Review/helpers/box';

describe('autoView', () => {
  const views: [number, number, number, number][] = [
    [5, 0.1, 0.2, 0.5],
    [10, 0, 0, 1],
  ];

  it('holds a view until the next one starts', () => {
    expect(autoView(views, 9.9, 100, 50)).toEqual({ x: 10, y: 10, w: 50, h: 25 });
    expect(autoView(views, 10, 100, 50)).toEqual({ x: 0, y: 0, w: 100, h: 50 });
  });

  it('shows the first one before it starts', () => {
    expect(autoView(views, 1, 100, 50)).toEqual({ x: 10, y: 10, w: 50, h: 25 });
  });
});

describe('boxAt', () => {
  const clip = {
    start: 1,
    end: 2,
    boxes: [
      [1, 0, 0, 10, 20],
      [1.5, 5, 0, 15, 20],
    ] as [number, number, number, number, number][],
  };

  it('takes the nearest box inside the clip', () => {
    expect(boxAt(clip, 1.4)).toEqual([5, 0, 15, 20]);
  });

  it('has no box outside the clip', () => {
    expect(boxAt(clip, 0.5)).toBeNull();
    expect(boxAt(clip, 2.5)).toBeNull();
  });
});

describe('viewAt', () => {
  // A 100 px tall player walking right across a 1600 x 900 frame.
  const clip = {
    start: 0,
    end: 2,
    boxes: [
      [0, 100, 400, 140, 500],
      [1, 700, 400, 740, 500],
      [2, 1500, 400, 1540, 500],
    ] as [number, number, number, number, number][],
  };

  it('spans 4 player heights at the frame aspect ratio, centered on the player', () => {
    expect(viewAt(clip, 1, 1600, 900)).toEqual({ x: 720 - 400 / 0.5625 / 2, y: 250, w: 400 / 0.5625, h: 400 });
  });

  it('stays inside the frame', () => {
    expect(viewAt(clip, 0, 1600, 900).x).toBe(0);
    expect(viewAt(clip, 2, 1600, 900).x).toBeCloseTo(1600 - 400 / 0.5625);
  });

  it('shows the whole frame without boxes', () => {
    expect(viewAt({ start: 0, end: 1, boxes: [] }, 0, 1600, 900)).toEqual({ x: 0, y: 0, w: 1600, h: 900 });
  });
});

describe('zoomView', () => {
  const all = { x: 0, y: 0, w: 1600, h: 900 };

  it('zooms around the point under the fingers, which stays put', () => {
    const v = zoomView(all, 0.25, 0.5, 2, 1600, 900)!;
    expect(v).toEqual({ x: 200, y: 225, w: 800, h: 450 });
    // The point at a quarter of the width, the middle of the height, before and after.
    expect(v.x + 0.25 * v.w).toBe(400);
    expect(v.y + 0.5 * v.h).toBe(450);
  });

  it('stays inside the frame, up to MAX_ZOOM, and gives the whole frame back at 1', () => {
    expect(zoomView(all, 0, 0, 2, 1600, 900)).toEqual({ x: 0, y: 0, w: 800, h: 450 });
    expect(1600 / zoomView(all, 0.5, 0.5, 100, 1600, 900)!.w).toBe(MAX_ZOOM);
    expect(zoomView({ x: 0, y: 0, w: 800, h: 450 }, 0.5, 0.5, 0.5, 1600, 900)).toBeNull();
  });
});

describe('panView', () => {
  it('moves the view inside the frame', () => {
    expect(panView({ x: 100, y: 100, w: 800, h: 450 }, 50, -500, 1600, 900)).toEqual({ x: 150, y: 0, w: 800, h: 450 });
    expect(panView({ x: 700, y: 100, w: 800, h: 450 }, 500, 0, 1600, 900).x).toBe(800);
  });
});

describe('wheelZoom', () => {
  it('follows a pinch and holds a mouse notch to a small step', () => {
    expect(wheelZoom(-10, 0)).toBeCloseTo(Math.exp(0.1));
    expect(wheelZoom(-120, 0)).toBeCloseTo(Math.exp(0.3));
    expect(wheelZoom(120, 0)).toBeCloseTo(Math.exp(-0.3));
  });

  it('counts lines as pixels', () => {
    expect(wheelZoom(-3, 1)).toBeCloseTo(Math.exp(0.3));
  });
});
