import { useCallback, useState } from 'react';

/** Which of a component's async actions runs, null when none: `run(key, action)` marks `key` until `action` settles, for
 * its button to show a loader and the others beside it to wait. */
export function useRunning<K extends string = string>() {
  const [running, setRunning] = useState<K | null>(null);
  const run = useCallback(async <T>(key: K, action: () => Promise<T>): Promise<T> => {
    setRunning(key);
    try {
      return await action();
    } finally {
      setRunning(null);
    }
  }, []);
  return [running, run] as const;
}

/** The page reloaded, the action that asked it running until it goes: its loader stays. */
export function reloading(): Promise<never> {
  location.reload();
  return new Promise<never>(() => {});
}
