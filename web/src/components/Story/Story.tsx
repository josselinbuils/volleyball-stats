import { useMemo } from 'react';
import { Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SetBadge } from '@/components/SetBadge';
import { setScores, setsWon } from '@/components/Header/helpers/score';
import { useFormat } from '@/lib/format';
import { groupName, hasTeams, match, playerLabel, rallies as allRallies } from '@/lib/match';
import { playerKey } from '@/helpers/players';
import { usePlayer } from '@/lib/player';
import { rallyClips } from '@/lib/playlist';
import { useSet } from '@/lib/sets';
import { Film } from '@/components/MyMatch/Film';
import { Curve } from '@/components/Story/Curve';
import { momentText } from '@/components/Story/helpers/momentText';
import { story, type Moment } from '@/components/Story/helpers/story';

/** The match as a story: the score gap rally after rally, then each set in plain sentences, each
 * moment replaying. */
export function Story() {
  const { t } = useTranslation();
  const { set, rallies } = useSet();
  const finals = useMemo(() => setScores(allRallies, match.scores), []);
  const chapters = useMemo(() => story(rallies, finals, (p) => playerKey(p, match.people)), [rallies, finals]);
  if (!hasTeams || !chapters.length) {
    return null;
  }
  const numbered = chapters.flatMap((c) => c.moments);
  const [won, lost] = setsWon(finals).sort((a, b) => b - a);
  const leader = setsWon(finals)[0] > setsWon(finals)[1] ? 1 : 2;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('story.title')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t('story.caption')}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {set === null && <p className="font-medium">{won === lost ? t('story.matchDraw', { count: won }) : t('story.match', { team: groupName(t, leader), count: won, lost })}</p>}
        {match.films?.['*'] && (
          <div className="flex flex-wrap gap-2">
            <Film name="*" label={t('story.film')} />
            <Film name="*wide" label={t('story.filmWide')} wide />
          </div>
        )}
        <Curve chapters={chapters} moments={numbered} />
        <div className="grid gap-6 lg:grid-cols-[repeat(auto-fit,minmax(18rem,1fr))]">
          {chapters.map((c) => (
            <section key={c.set} className="grid content-start gap-2">
              <h3 className="font-semibold">{t('story.setTitle', { n: c.set, team: c.winner ? groupName(t, c.winner) : '', score: c.score.join('-') })}</h3>
              <p className="text-sm text-muted-foreground">
                {t(`story.shape.${c.shape}`, { count: c.deficit })}
                {c.top && ` ${t('story.top', { count: c.top.points, name: playerLabel(t, c.top.person) })}`}
              </p>
              {c.moments.length > 0 && (
                <ol className="m-0 grid list-none gap-1 p-0">
                  {c.moments.map((m) => (
                    <MomentRow key={`${m.kind}:${m.rallies[0]}`} moment={m} number={numbered.indexOf(m) + 1} />
                  ))}
                </ol>
              )}
            </section>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function MomentRow({ moment: m, number }: { moment: Moment; number: number }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { play } = usePlayer();
  const text = momentText(t, m, f.secs);
  return (
    <li>
      <button
        type="button"
        title={t('story.replay')}
        onClick={() =>
          play(
            (tr) => momentText(tr, m, f.secs),
            rallyClips(
              allRallies.filter((r) => m.rallies.includes(r.i)),
              match.duration,
            ),
          )
        }
        className="group flex w-full items-start gap-2 rounded-md px-1.5 py-1 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span aria-hidden className="inline-grid size-5 shrink-0 place-items-center rounded-full bg-foreground text-xs font-semibold text-background tabular-nums">
          {number}
        </span>
        <span className="min-w-0 flex-1">{text}</span>
        <Play aria-hidden className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
      </button>
    </li>
  );
}
