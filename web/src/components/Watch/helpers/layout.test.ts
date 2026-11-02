import { describe, expect, it } from 'vitest';
import { arrange, clampRatio, defaultLayout, GAP, pageHeight, parsed, stacked, swapped, swappedSides, toggled, type View } from '@/components/Watch/helpers/layout';

describe('layout', () => {
  const two = { ...defaultLayout(['video', '2d'] as View[]), x: 0.6 };
  const three = defaultLayout(['video', '2d', '3d']);
  const four = defaultLayout(['video', '2d', '3d', 'tv']);

  describe('arrange', () => {
    it('gives one view the whole space, without a bar', () => {
      const { rects, dividers } = arrange(defaultLayout(['3d']), 1000, 500);
      expect(rects['3d']).toEqual({ left: 0, top: 0, width: 1000, height: 500 });
      expect(dividers).toEqual([]);
    });

    it('splits two views at x, a gap between them', () => {
      const { rects, dividers } = arrange(two, 1000, 500);
      expect(rects.video).toEqual({ left: 0, top: 0, width: 600 - GAP / 2, height: 500 });
      expect(rects['2d']).toEqual({ left: 600 + GAP / 2, top: 0, width: 400 - GAP / 2, height: 500 });
      expect(dividers).toEqual([{ ratio: 'x', axis: 'x', at: 600, start: 0, length: 500 }]);
    });

    it('stacks the last two of three on the side, flip putting them on the left', () => {
      const { rects, dividers } = arrange(three, 1000, 500);
      expect(rects.video?.height).toBe(500);
      expect(rects['2d']?.top).toBe(0);
      expect(rects['3d']?.top).toBe(250 + GAP / 2);
      expect(dividers[1]).toEqual({ ratio: 'y', axis: 'y', at: 250, start: 600, length: 400 });
      const flipped = arrange({ ...three, flip: true, x: 0.4 }, 1000, 500);
      expect(flipped.rects.video?.left).toBe(400 + GAP / 2);
      expect(flipped.dividers[1]).toEqual({ ratio: 'y', axis: 'y', at: 250, start: 0, length: 400 });
    });

    it('makes a grid of four, the two bars crossing', () => {
      const { rects, dividers } = arrange(four, 1000, 500);
      expect(rects.tv).toEqual({ left: 600 + GAP / 2, top: 250 + GAP / 2, width: 400 - GAP / 2, height: 250 - GAP / 2 });
      expect(dividers[0]).toMatchObject({ ratio: 'x', at: 600, length: 500 });
      expect(dividers[1]).toMatchObject({ ratio: 'y', at: 250, length: 1000 });
    });

    it('turns a quarter on a tall screen', () => {
      const { rects, dividers } = arrange(two, 500, 1000, true);
      expect(rects.video).toEqual({ left: 0, top: 0, width: 500, height: 600 - GAP / 2 });
      expect(dividers[0]).toMatchObject({ axis: 'y', at: 600, length: 500 });
    });

    it('fills the space with every number of views', () => {
      for (const layout of [two, three, four]) {
        const rects = Object.values(arrange(layout, 1000, 500).rects);
        const area = rects.reduce((sum, r) => sum + r.width * r.height, 0);
        expect(area).toBeGreaterThan(1000 * 500 * 0.98);
        expect(area).toBeLessThanOrEqual(1000 * 500);
      }
    });
  });

  it('stacks views at their own shape on a phone', () => {
    const { rects, height, dividers } = stacked(['video', '3d'], 320);
    expect(rects.video).toEqual({ left: 0, top: 0, width: 320, height: 180 });
    expect(rects['3d']).toEqual({ left: 0, top: 180 + GAP, width: 320, height: 180 });
    expect(height).toBe(180 + GAP + 180);
    expect(dividers).toEqual([]);
    expect(stacked(['video', '3d', 'tv'], 320).swaps).toEqual([
      { at: 180 + GAP / 2, between: ['video', '3d'] },
      { at: 2 * 180 + GAP + GAP / 2, between: ['3d', 'tv'] },
    ]);
  });

  describe('pageHeight', () => {
    it('follows the tallest column, up to the cap', () => {
      expect(pageHeight(two, 1600, 1000)).toBeCloseTo((960 * 9) / 16);
      expect(pageHeight({ ...two, x: 0.2 }, 1600, 1000)).toBeCloseTo(1280 / 1.75);
      expect(pageHeight(two, 1600, 300)).toBe(300);
    });

    it('adds the views of a column', () => {
      expect(pageHeight({ ...three, x: 0.5 }, 1000, 2000)).toBeCloseTo(500 / 1.75 + (500 * 9) / 16);
    });
  });

  describe('toggled', () => {
    it('adds a view last and removes one', () => {
      expect(toggled(two, 'tv').order).toEqual(['video', '2d', 'tv']);
      expect(toggled(two, 'video').order).toEqual(['2d']);
    });

    it('starts the sizes over: three with level columns, four equal, two with the first larger', () => {
      const added = toggled(two, '3d');
      const [left, right] = [(1000 * added.x * 9) / 16, 1000 * (1 - added.x) * (1 / 1.75 + 9 / 16)];
      expect(left).toBeCloseTo(right);
      expect(toggled({ ...three, x: 0.3 }, 'tv')).toMatchObject({ x: 0.5, y: 0.5 });
      expect(toggled({ ...three, x: 0.3 }, '3d').x).toBe(0.6);
    });

    it('levels three flipped from the other side', () => {
      const added = toggled({ ...two, flip: true }, '3d');
      expect(added.x).toBeCloseTo(1 - toggled(two, '3d').x);
    });

    it('keeps the last view', () => {
      const one = defaultLayout(['tv']);
      expect(toggled(one, 'tv')).toBe(one);
    });
  });

  describe('swapped', () => {
    it('lets two views keep their sizes', () => {
      const next = swapped(two, 'video', '2d');
      expect(next.order).toEqual(['2d', 'video']);
      expect(next.x).toBeCloseTo(0.4);
    });

    it('leaves the sizes to the places with more views', () => {
      const next = swapped(three, '3d', 'video');
      expect(next.order).toEqual(['3d', '2d', 'video']);
      expect(next.x).toBe(three.x);
    });
  });

  describe('swappedSides', () => {
    it('inverts two views and comes back', () => {
      const next = swappedSides(two, 'x');
      expect(next.order).toEqual(['2d', 'video']);
      expect(next.x).toBeCloseTo(0.4);
      expect(swappedSides(next, 'x').order).toEqual(two.order);
    });

    it('moves the tall view of three to the other side', () => {
      const next = swappedSides(three, 'x');
      expect(next.flip).toBe(true);
      expect(next.order).toEqual(three.order);
    });

    it('swaps the rows of three and of four', () => {
      expect(swappedSides(three, 'y').order).toEqual(['video', '3d', '2d']);
      expect(swappedSides(four, 'y').order).toEqual(['3d', 'tv', 'video', '2d']);
    });

    it('swaps the columns of four', () => {
      expect(swappedSides(four, 'x').order).toEqual(['2d', 'video', 'tv', '3d']);
    });
  });

  describe('parsed', () => {
    it('keeps a stored layout, without what the page cannot show', () => {
      const stored = { order: ['video', '2d', '3d'], x: 0.7, y: 0.3, flip: true };
      expect(parsed(stored, ['2d', '3d', 'tv'])).toEqual({ order: ['2d', '3d'], x: 0.7, y: 0.3, flip: true });
    });

    it('refuses what makes no sense', () => {
      expect(parsed(null, ['2d'])).toBeNull();
      expect(parsed({ order: 'video' }, ['2d'])).toBeNull();
      expect(parsed({ order: ['video'] }, ['2d'])).toBeNull();
    });

    it('holds the ratios within bounds and drops repeated views', () => {
      const layout = parsed({ order: ['2d', '2d'], x: 5, y: 'a' }, ['2d']);
      expect(layout).toEqual({ order: ['2d'], x: clampRatio(5), y: 0.5, flip: false });
    });
  });
});
