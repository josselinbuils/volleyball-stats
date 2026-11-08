import { describe, expect, it } from 'vitest';
import type { ListedMatch } from '@/components/Matches';
import { withRemote } from '@/lib/remoteMatches';

const listed = (path: string, date: string | null, remote = false): ListedMatch => ({ path, name: path, date, title: null, teams: null, scores: [], sets: 0, rallies: 0, remote });

describe('withRemote', () => {
  it('slots the server matches among those here, newest first', () => {
    const here = [listed('2026-11-02-b', '2026-11-02'), listed('2026-10-01-a', '2026-10-01')];
    const out = withRemote(here, [listed('2026-10-29-c', '2026-10-29', true), listed('undated', null, true)]);
    expect(out.map((m) => m.path)).toEqual(['2026-11-02-b', '2026-10-29-c', '2026-10-01-a', 'undated']);
  });

  it('keeps the copy here of a match also on the server', () => {
    const out = withRemote([listed('m', '2026-10-29')], [listed('m', '2026-10-29', true)]);
    expect(out).toHaveLength(1);
    expect(out[0].remote).toBe(false);
  });
});
