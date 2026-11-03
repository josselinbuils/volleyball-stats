import { useTranslation } from 'react-i18next';
import { Play, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { GROUPS, groupName, match, teamColor, teamRing } from '@/lib/match';
import type { Timeout, TimeoutChange } from '@/lib/review';

/** The timeouts found and corrected: each one's team to pick, removed if it is none; one added where the video stands. */
export function Timeouts({ timeouts, now, onGo, onChange }: { timeouts: Timeout[]; now: number; onGo: (time: number) => void; onChange: (change: TimeoutChange) => void }) {
  const { t } = useTranslation();
  const frame = Math.round(now * match.fps);
  const inOne = timeouts.some((o) => o.start <= frame && frame < o.end);
  return (
    <section className="grid gap-2 lg:col-span-2" aria-labelledby="timeouts-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id="timeouts-title" className="text-base font-semibold">
          {t('review.timeoutsTitle')}
        </h3>
        <Button variant="outline" size="sm" className="bg-card tabular-nums" disabled={inOne} onClick={() => onChange({ frame })}>
          <Plus aria-hidden />
          {t('review.timeoutAdd', { at: clock(now) })}
        </Button>
      </div>
      {timeouts.length === 0 && <p className="text-sm text-muted-foreground">{t('review.noTimeouts')}</p>}
      <ol className="grid gap-2">
        {timeouts.map((o) => (
          <li key={o.start} className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2 rounded-md bg-muted/50 px-3 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" className="bg-card tabular-nums" title={t('review.reportGo')} onClick={() => onGo(o.start / match.fps)}>
                <Play aria-hidden className="fill-current" />
                {clock(o.start / match.fps)}
              </Button>
              {GROUPS.map((g) => (
                <Button
                  key={g}
                  variant={o.team === g ? 'default' : 'outline'}
                  size="sm"
                  className={o.team === g ? undefined : 'bg-card'}
                  aria-pressed={o.team === g}
                  onClick={() => onChange({ start: o.start, end: o.end, team: o.team === g ? null : g })}
                >
                  <Swatch color={teamColor(g)} ring={teamRing(g)} />
                  {groupName(t, g)}
                </Button>
              ))}
            </div>
            <Button variant="ghost" size="icon-sm" title={t('review.timeoutRemove')} aria-label={t('review.timeoutRemove')} onClick={() => onChange({ start: o.start, end: o.end, removed: true })}>
              <X aria-hidden />
            </Button>
          </li>
        ))}
      </ol>
    </section>
  );
}
