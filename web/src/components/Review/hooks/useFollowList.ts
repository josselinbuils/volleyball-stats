import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react';
import { railAt, shiftOf, topOf } from '@/components/Review/helpers/timeline';

/** After the user scrolls the list, it stops following the video this long. */
const HOLD_MS = 3000;
// How often the list checks on the rail's end, and how near its edges that end may come, in pixels.
const RAIL_FOLLOW_PX = 24;
const RAIL_EDGE_PX = 64;

/** The touches' list (`list`) following the video at `now`: the row `current` names centred (`centre` brings any row),
 * else the rail's end kept in view between rallies; never while a field in it is being filled (`setEditing`) or for a
 * while after the user scrolled it (`place`, where it stood, kept across its remounts). `first`, the first rally listed:
 * rallies joining the list or leaving it keep the rows still there in place. `rail`: how far the time has come along the
 * list, and its height. */
export function useFollowList(place: RefObject<{ top: number; scrolled: number }>, current: string, first: number, now: number) {
  const list = useRef<HTMLOListElement>(null);
  const [editing, setEditing] = useState(false);
  useLayoutEffect(() => {
    if (list.current) {
      list.current.scrollTop = place.current.top;
    }
  }, []);
  const centre = (key: string) => {
    const box = list.current;
    const item = box?.querySelector<HTMLElement>(`[data-key="${key}"]`);
    box?.scrollTo({ top: item ? topOf(item) - (box.clientHeight - item.offsetHeight) / 2 : 0, behavior: 'smooth' });
    return item;
  };
  useEffect(() => {
    if (!editing && Date.now() - place.current.scrolled > HOLD_MS) {
      centre(current);
    }
    // `first`: keeping the rows in place when the rallies around change stops the scroll under way.
  }, [current, editing, first]);
  // The rail along the list: how far the time has come, between rallies too, where no row is lit.
  const [rail, setRail] = useState({ at: 0, height: 0 });
  const placed = useRef({ first, tops: new Map<string, number>() });
  useLayoutEffect(() => {
    const box = list.current;
    const rows = [...(box?.querySelectorAll<HTMLElement>('[data-at]') ?? [])].map((e) => ({ key: e.dataset.key, at: Number(e.dataset.at), top: topOf(e), bottom: topOf(e) + e.offsetHeight }));
    // Rallies leaving the list or joining it must not move the rows still there on screen.
    const tops = new Map(rows.flatMap((r) => (r.key ? [[r.key, r.top] as const] : [])));
    if (box && placed.current.first !== first) {
      box.scrollTop += shiftOf(placed.current.tops, tops);
    }
    placed.current = { first, tops };
    const at = railAt(rows, now);
    const height = rows.at(-1)?.bottom ?? 0;
    setRail((r) => (Math.abs(r.at - at) < 1 && r.height === height ? r : { at, height }));
  });
  // Between rallies, no row is centred: the list follows the rail's end when it nears an edge.
  const railStep = Math.round(rail.at / RAIL_FOLLOW_PX);
  useEffect(() => {
    const box = list.current;
    // No height yet: the rail is not measured.
    if (box && rail.height && !editing && Date.now() - place.current.scrolled > HOLD_MS && (rail.at < box.scrollTop + RAIL_EDGE_PX || rail.at > box.scrollTop + box.clientHeight - RAIL_EDGE_PX)) {
      box.scrollTo({ top: rail.at - box.clientHeight / 2, behavior: 'smooth' });
    }
  }, [railStep]);
  return { list, setEditing, rail, centre };
}
