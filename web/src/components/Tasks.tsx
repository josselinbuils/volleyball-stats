import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Check, CircleAlert, LoaderCircle } from 'lucide-react';
import { ErrorNote } from '@/components/ErrorNote';
import { JobProgress, useDuration } from '@/components/JobProgress';
import { explain } from '@/lib/errors';
import { isHere, taskHref, useShownTasks, useTasks, type Task } from '@/lib/tasks';
import { cn } from '@/lib/utils';

// A task ended well shows this long; one failed stays until its panel closes.
const DONE_MS = 4000;

type Ended = { task: Task; failed: boolean; at: number };

/** A task in a few words: the review's step, else the job's kind. */
export function taskLabel(t: TFunction, task: Task): string {
  if (task.kind === 'review') {
    return t(`review.step.${task.step}`, { defaultValue: t('review.applying') }).replace(/…$/, '');
  }
  return t(`tasks.kind.${task.kind}`, { defaultValue: task.kind });
}

/** The running step's stage, when the task tells one. */
function detail(t: TFunction, task: Task): string | null {
  if (!task.stage) {
    return null;
  }
  return task.kind === 'review' ? t(`review.stage.${task.stage}`, { defaultValue: task.stage }) : t(`server.stage.${task.stage}`, { n: task.n, of: task.of, defaultValue: '' }) || null;
}

/** The share done, as the bars say it: never 100 % before the end. */
function usePercent() {
  const { i18n } = useTranslation();
  return (x: number) => new Intl.NumberFormat(i18n.language, { style: 'percent', maximumFractionDigits: 0 }).format(Math.min(0.99, Math.max(0, x)));
}

/** A ring filled by the share done, else turning. */
function Ring({ fraction }: { fraction: number | null | undefined }) {
  if (fraction == null) {
    return <LoaderCircle aria-hidden className="size-4 shrink-0 animate-spin" />;
  }
  const r = 6;
  const around = 2 * Math.PI * r;
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="size-4 shrink-0 -rotate-90">
      <circle cx="8" cy="8" r={r} fill="none" strokeWidth="2.5" className="stroke-muted" />
      <circle
        cx="8"
        cy="8"
        r={r}
        fill="none"
        strokeWidth="2.5"
        className="stroke-primary transition-[stroke-dashoffset] duration-300"
        strokeDasharray={around}
        strokeDashoffset={around * (1 - fraction)}
      />
    </svg>
  );
}

/** The app's background tasks on every page of the app: a pill in the corner (the task, its share and the time left),
 * opening a panel with each one's bar and a link to its screen; the tasks a bar of the page shows are left out. A task
 * ended well says so a moment, one failed stays until its panel closes. The share also leads the window's title. */
export function Tasks() {
  const { t } = useTranslation();
  const all = useTasks();
  const shown = useShownTasks();
  const duration = useDuration();
  const percent = usePercent();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // The tasks seen running at the last poll: one gone or ended since then has ended here.
  const before = useRef(new Map<string, Task>());
  const [ended, setEnded] = useState<Ended[]>([]);
  useEffect(() => {
    const now = new Map(all.filter((task) => task.running).map((task) => [task.id, task]));
    const gone = [...before.current.values()]
      .filter((task) => !now.has(task.id))
      .map((task) => {
        const after = all.find((a) => a.id === task.id);
        return { task: { ...task, ...after }, failed: !!after?.failed, at: Date.now() };
      });
    before.current = now;
    setEnded((list) => {
      const kept = list.filter((e) => !now.has(e.task.id) && !gone.some((g) => g.task.id === e.task.id));
      // The same list when nothing ended or started again, for the done ones' timer to run its course.
      return gone.length || kept.length !== list.length ? [...kept, ...gone] : list;
    });
  }, [all]);
  useEffect(() => {
    if (!ended.some((e) => !e.failed)) {
      return;
    }
    const timer = window.setTimeout(() => setEnded((list) => list.filter((e) => e.failed || Date.now() - e.at < DONE_MS)), DONE_MS);
    return () => window.clearTimeout(timer);
  }, [ended]);

  const running = all.filter((task) => task.running && !shown.has(task.id));
  const failures = ended.filter((e) => e.failed && !shown.has(e.task.id));
  const done = ended.filter((e) => !e.failed && !shown.has(e.task.id));

  // The window's title leads with the share of the first task telling one, its bar here or not.
  const lead = all.find((task) => task.running && task.fraction != null);
  const prefix = lead ? `${percent(lead.fraction!)} · ` : '';
  useEffect(() => {
    const strip = (title: string) => title.replace(/^\d+[\s  ]?%\s·\s/, '');
    const apply = () => {
      const want = prefix + strip(document.title);
      if (document.title !== want) {
        document.title = want;
      }
    };
    apply();
    const observer = new MutationObserver(apply);
    const title = document.querySelector('title');
    if (title) {
      observer.observe(title, { childList: true, characterData: true, subtree: true });
    }
    return () => {
      observer.disconnect();
      document.title = strip(document.title);
    };
  }, [prefix]);

  // The panel closes on Escape or a press elsewhere; the failures it showed go with it.
  const close = () => {
    setOpen(false);
    setEnded((list) => list.filter((e) => !e.failed));
  };
  useEffect(() => {
    if (!open) {
      return;
    }
    const away = (event: PointerEvent) => !box.current?.contains(event.target as Node) && close();
    const key = (event: KeyboardEvent) => event.key === 'Escape' && close();
    document.addEventListener('pointerdown', away);
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('pointerdown', away);
      document.removeEventListener('keydown', key);
    };
  }, [open]);
  useEffect(() => {
    if (open && !running.length && !failures.length && !done.length) {
      setOpen(false);
    }
  }, [open, running.length, failures.length, done.length]);

  if (!running.length && !failures.length && !done.length) {
    return null;
  }
  const one = running.length === 1 ? running[0] : null;
  const pill = failures.length ? (
    <>
      <CircleAlert aria-hidden className="size-4 shrink-0" />
      <span className="truncate">{t('tasks.failed', { task: taskLabel(t, failures[0].task) })}</span>
    </>
  ) : one ? (
    <>
      <Ring fraction={one.fraction} />
      <span className="truncate">{taskLabel(t, one)}</span>
      <span className="shrink-0 text-muted-foreground tabular-nums">{[one.fraction != null && percent(one.fraction), one.left != null && duration(one.left)].filter(Boolean).join(' · ')}</span>
    </>
  ) : running.length ? (
    <>
      <LoaderCircle aria-hidden className="size-4 shrink-0 animate-spin" />
      <span className="truncate">{t('tasks.count', { count: running.length })}</span>
    </>
  ) : (
    <>
      <Check aria-hidden className="size-4 shrink-0 text-primary" />
      <span className="truncate">{t('tasks.done', { task: taskLabel(t, done[done.length - 1].task) })}</span>
    </>
  );

  const title = (task: Task) => {
    const teams = task.teams?.filter(Boolean);
    return teams?.length === 2 ? t('matchTitle', { one: teams[0], two: teams[1] }) : null;
  };
  const see = (task: Task) => {
    const href = taskHref(task);
    return isHere(href) ? null : (
      <a href={href} className="shrink-0 text-sm font-medium text-primary underline-offset-4 hover:underline" onClick={close}>
        {t('tasks.see')}
      </a>
    );
  };
  const head = (task: Task) => (
    <div className="flex items-baseline justify-between gap-3">
      <p className="m-0 min-w-0 text-sm">
        <span className="font-medium">{taskLabel(t, task)}</span>
        {title(task) && <span className="text-muted-foreground"> · {title(task)}</span>}
      </p>
      {see(task)}
    </div>
  );

  return (
    <div ref={box} className="pointer-events-none fixed right-4 bottom-4 z-40 flex flex-col items-end gap-2 max-sm:left-4">
      {open && (
        <div role="dialog" aria-label={t('tasks.title')} className="pointer-events-auto grid w-80 max-w-full gap-4 rounded-lg border bg-popover p-3 text-popover-foreground shadow-md max-sm:w-full">
          {failures.map(({ task }) => (
            <div key={task.id} className="grid gap-1">
              {head(task)}
              <ErrorNote {...explain(t, task.error)} />
            </div>
          ))}
          {running.map((task) => (
            <div key={task.id} className="grid gap-1">
              {head(task)}
              <JobProgress label={taskLabel(t, task)} fraction={task.fraction ?? null} part={task.part} left={task.left} elapsed={task.elapsed} late={task.late}>
                {detail(t, task)}
              </JobProgress>
            </div>
          ))}
          {done.map(({ task }) => (
            <div key={task.id} className="grid gap-1">
              {head(task)}
              <p className="m-0 flex items-center gap-1.5 text-sm text-muted-foreground">
                <Check aria-hidden className="size-4 text-primary" />
                {t('tasks.ended')}
              </p>
            </div>
          ))}
        </div>
      )}
      <button
        type="button"
        aria-expanded={open}
        onClick={() => (open ? close() : setOpen(true))}
        className={cn(
          'pointer-events-auto flex h-9 max-w-full items-center gap-2 rounded-full border bg-popover px-3.5 text-sm text-popover-foreground shadow-md outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 max-sm:w-full max-sm:rounded-lg',
          failures.length > 0 && 'border-destructive/50 text-destructive',
        )}
      >
        {pill}
      </button>
    </div>
  );
}
