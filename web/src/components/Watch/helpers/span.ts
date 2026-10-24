import type { Rally } from '@/lib/match';
import { AFTER, PAD } from '@/lib/playlist';

/** The stretch of video the filter allows: the whole video with every rally shown (`all`), else
 * from a rally clip's start before the first shown rally, where the score turns to its set, to a
 * touch clip's end after the last. */
export function span(rallies: Rally[], all: boolean, duration: number): { start: number; end: number } {
  if (all || !rallies.length) {
    return { start: 0, end: duration };
  }
  return { start: Math.max(0, rallies[0].start - PAD), end: Math.min(duration, rallies[rallies.length - 1].end + AFTER) };
}
