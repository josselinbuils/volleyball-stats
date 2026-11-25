import { useEffect, useState } from 'react';
import { readFailure, type Failure } from '@/lib/review';

/** Where the server's run stands: its step (and the pipeline's stage), which of how many, the time spent and left, and
 * whether it takes longer than last time. */
export type RunProgress = { fraction: number; part: number | null; step: string; stage: string | null; n: number; of: number; elapsed: number; left: number; late: boolean };

/** The server's run as `progress`, followed by `watch` (its timer returned, `ended` once none goes). A run going as the page
 * opened (`running`) is followed at once: the page reloaded once it ends, else `onFailed` given why. */
export function useRunProgress(running: string | undefined, onFailed: (failure: Failure) => void) {
  const [progress, setProgress] = useState<RunProgress | null>(null);
  const watch = (ended?: () => void) =>
    window.setInterval(async () => {
      try {
        const p = (await (await fetch('progress')).json()) as {
          steps?: string[];
          done: number;
          stage: string | null;
          elapsed: number;
          left: number;
          late: boolean;
          part?: number | null;
          fraction: number;
        };
        if (p.steps) {
          setProgress({
            fraction: p.fraction,
            part: p.part ?? null,
            step: p.steps[p.done],
            stage: p.stage,
            n: p.done + 1,
            of: p.steps.length,
            elapsed: p.elapsed,
            left: p.left,
            late: p.late,
          });
        } else {
          ended?.();
        }
      } catch {
        // The bar waits for the next poll.
      }
    }, 400);
  useEffect(() => {
    if (!running) {
      return;
    }
    let over = false;
    const timer = watch(async () => {
      if (over) {
        return;
      }
      over = true;
      window.clearInterval(timer);
      const failed = await readFailure();
      if (!failed) {
        location.reload();
        return;
      }
      setProgress(null);
      onFailed(failed);
    });
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, as the page opens
  }, [running]);
  return { progress, setProgress, watch };
}
