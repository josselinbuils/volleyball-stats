import { useEffect, useState, useSyncExternalStore } from 'react';

/** A background task of the app (app.tasks): the review's run (`review`) or a job, running or just ended. */
export type Task = {
  id: string;
  kind: string;
  running: boolean;
  match?: string | null;
  teams?: (string | null)[] | null;
  step?: string | null;
  stage?: string | null;
  n?: number | null;
  of?: number | null;
  fraction?: number | null;
  part?: number | null;
  left?: number | null;
  elapsed?: number;
  late?: boolean;
  failed?: boolean;
  error?: string | null;
};

const RUNNING_MS = 2000;
const IDLE_MS = 10_000;

let tasks: Task[] = [];
const listeners = new Set<() => void>();
let timer: number | undefined;

async function poll() {
  try {
    const response = await fetch('/app/tasks');
    if (response.ok) {
      const found: unknown = await response.json();
      if (Array.isArray(found)) {
        tasks = found as Task[];
        listeners.forEach((listener) => listener());
      }
    }
  } catch {
    // The next poll tries again.
  }
  if (listeners.size) {
    timer = window.setTimeout(poll, tasks.some((task) => task.running) ? RUNNING_MS : IDLE_MS);
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    void poll();
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      window.clearTimeout(timer);
    }
  };
}

const none: Task[] = [];
const idle = () => () => {};

/** The app's tasks, asked of its server every few seconds while one runs: only on the app's pages (`on`). */
export function useTasks(on = true): Task[] {
  return useSyncExternalStore(on ? subscribe : idle, () => (on ? tasks : none));
}

// The tasks a bar of this page already shows, kept on the window: the page, the review and the app's screens are
// bundles of their own.
declare global {
  interface Window {
    shownTasks?: Map<string, number>;
  }
}
const SHOWN = 'shown-tasks';

/** Marks the task `id` shown by a bar of this page while it is there: the pill leaves it out. */
export function useShownHere(id: string | null | undefined) {
  useEffect(() => {
    if (!id) {
      return;
    }
    const shown = (window.shownTasks ??= new Map());
    shown.set(id, (shown.get(id) ?? 0) + 1);
    window.dispatchEvent(new Event(SHOWN));
    return () => {
      const n = (shown.get(id) ?? 1) - 1;
      if (n) {
        shown.set(id, n);
      } else {
        shown.delete(id);
      }
      window.dispatchEvent(new Event(SHOWN));
    };
  }, [id]);
}

/** The ids of the tasks a bar of this page shows. */
export function useShownTasks(): Set<string> {
  const read = () => new Set(window.shownTasks?.keys() ?? []);
  const [shown, setShown] = useState(read);
  useEffect(() => {
    const update = () => setShown(read());
    update();
    window.addEventListener(SHOWN, update);
    return () => window.removeEventListener(SHOWN, update);
  }, []);
  return shown;
}

/** Where a task's own screen is, from any page of the app. */
export function taskHref(task: Task): string {
  if (task.kind === 'review') {
    return '/review';
  }
  return ['hosting', 'backup', 'verify', 'export'].includes(task.kind) ? '/matches/#site' : '/matches/';
}

/** Whether `href` is the screen shown: the list's tabs are its hashes, the review's are one screen. */
export function isHere(href: string, where: Location = location): boolean {
  const [path, hash] = href.split('#');
  if (where.pathname !== path) {
    return false;
  }
  return hash !== undefined ? where.hash === `#${hash}` : path !== '/matches/' || !where.hash;
}
