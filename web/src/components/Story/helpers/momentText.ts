import type { TFunction } from 'i18next';
import { groupName, playerLabel } from '@/lib/match';
import type { Moment } from '@/components/Story/helpers/story';

/** A moment in a sentence. */
export function momentText(tr: TFunction, m: Moment, seconds: (s: number) => string): string {
  const name = m.person === null ? null : playerLabel(tr, m.person);
  const scores = { from: m.from.join('-'), to: m.to.join('-') };
  const team = m.team ? groupName(tr, m.team) : '';
  if (m.kind === 'run') {
    return tr(name ? 'story.runServer' : 'story.run', { team, n: m.n, name, ...scores });
  }
  if (m.kind === 'comeback') {
    return tr('story.comeback', { team, n: m.n, ...scores });
  }
  if (m.kind === 'setPoints') {
    return tr('story.setPoints', { team, count: m.n, ...scores });
  }
  return tr(name ? 'story.longestScorer' : 'story.longest', { n: m.n, name, seconds: seconds(m.seconds) });
}
