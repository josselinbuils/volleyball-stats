import { useEffect, useRef, type RefObject } from 'react';
import type { Edit, ReportChanges, Was } from '@/lib/review';

// The corrections save themselves this long after the last edit.
const AUTOSAVE_MS = 1000;

/** The Match tab's saves: `changes` save themselves `AUTOSAVE_MS` after the last edit, at once on another rally (`here`), on
 * leaving (`flush`, set to it) and once the editor goes. Each save unchecks the rallies checked it changes (`changedIn`, by
 * their key), with what they were when checked (`wasOf`) to put them back. `send` saves a body now, `autosave` what waits:
 * whether it went. */
export function useAutosave({
  changes,
  saved,
  checked,
  here,
  flush,
  onSend,
  changedIn,
  wasOf,
}: {
  changes: ReportChanges;
  saved: Partial<ReportChanges>;
  checked: Set<number>;
  here: number | undefined;
  flush: RefObject<(() => Promise<boolean>) | null>;
  onSend: (body: Edit) => Promise<boolean>;
  changedIn: (c: ReportChanges, from: Partial<ReportChanges>) => Set<number>;
  wasOf: (key: number, from: Partial<ReportChanges>) => Was | null;
}) {
  // What the saves sent make, those under way too: each next one is reckoned from it. Back to what the server says once
  // none is under way.
  const base = useRef({ changes: saved, checked });
  const underWay = useRef(0);
  const lastSave = useRef<Promise<boolean>>(Promise.resolve(true));
  // What a save that failed unchecked: the next one does it.
  const owed = useRef<{ unchecked: number[]; was: Record<number, Was> }>({ unchecked: [], was: {} });
  useEffect(() => {
    if (!underWay.current) {
      base.current = { changes: saved, checked };
    }
  });
  /** Saves `body`, the rallies checked it changes unchecked with it (but those it checks or unchecks), and what they were
   * when checked: to put them back. */
  const send = (body: Edit & { changes: ReportChanges }): Promise<boolean> => {
    const { changes: before, checked: on } = base.current;
    const said = new Set([...(body.checked ?? []), ...(body.unchecked ?? [])]);
    const off = [...changedIn(body.changes, before)].filter((k) => on.has(k) && !said.has(k));
    const owing = owed.current;
    owed.current = { unchecked: [], was: {} };
    const later = [...new Set([...owing.unchecked, ...off])].filter((k) => !said.has(k));
    const was: Record<number, Was> = { ...owing.was };
    for (const k of off) {
      const w = wasOf(k, before);
      if (w) {
        was[k] = w;
      }
    }
    const kept = Object.fromEntries(Object.entries(was).filter(([k]) => later.includes(Number(k))));
    const unchecked = [...(body.unchecked ?? []), ...later];
    const full: Edit = {
      ...body,
      ...(unchecked.length ? { unchecked } : {}),
      ...(Object.keys(kept).length ? { was: kept } : {}),
    };
    base.current = { changes: body.changes, checked: new Set([...[...on].filter((k) => !unchecked.includes(k)), ...(body.checked ?? [])]) };
    underWay.current++;
    const done = onSend(full)
      .then((ok) => {
        if (!ok) {
          owed.current = { unchecked: [...new Set([...owed.current.unchecked, ...later])], was: { ...kept, ...owed.current.was } };
        }
        return ok;
      })
      .finally(() => underWay.current--);
    lastSave.current = done;
    return done;
  };
  // What the last save sent is not sent again.
  const autosave = () => (changedIn(changes, base.current.changes).size ? send({ changes }) : lastSave.current);
  const latest = useRef(autosave);
  latest.current = autosave;
  const text = JSON.stringify(changes);
  useEffect(() => {
    const timer = window.setTimeout(() => void latest.current(), AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [text]);
  useEffect(() => void latest.current(), [here]);
  useEffect(() => {
    flush.current = () => latest.current();
    return () => {
      flush.current = null;
      void latest.current();
    };
  }, []);
  return { send, autosave };
}
