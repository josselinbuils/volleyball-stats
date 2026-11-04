import type { Comparison } from '@/lib/review';

/** `measures` by how the run changed their share right; one with nothing to compare on either side is left out. */
export function compared({ before, after }: Comparison, measures: string[]): { better: string[]; worse: string[]; same: number } {
  const better: string[] = [];
  const worse: string[] = [];
  let same = 0;
  for (const key of measures) {
    const [was, then] = before[key] ?? [0, 0];
    const [now, total] = after[key] ?? [0, 0];
    if (!then || !total) {
      continue;
    }
    const change = now * then - was * total;
    if (change > 0) {
      better.push(key);
    } else if (change < 0) {
      worse.push(key);
    } else {
      same++;
    }
  }
  return { better, worse, same };
}
