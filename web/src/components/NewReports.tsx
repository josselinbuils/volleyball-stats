import { useEffect, useRef, useState } from 'react';
import { Flag, FolderOpen, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { ErrorNote } from '@/components/ErrorNote';
import { explain, type Explained } from '@/lib/errors';
import { openMatch } from '@/lib/openMatch';

const EVERY_MS = 60_000;

type News = { name: string; count: number; teams: (string | null)[] | null };

/** The viewers' reports the app fetched (`feedback.watch`) and no review has shown yet, by match: shown here, and in a
 * notification of the system when more come while the page is open (allowed at the first click on the notice). `mayLeave`
 * asks before the page goes. */
export function NewReports({ mayLeave = async () => true }: { mayLeave?: () => Promise<boolean> }) {
  const { t } = useTranslation();
  const [news, setNews] = useState<News[]>([]);
  // The match open here (null: the list), its new reports shown by a reload.
  const [current, setCurrent] = useState<string | null>(null);
  const [going, setGoing] = useState<string | null>(null);
  const [error, setError] = useState<Explained | null>(null);
  // The counts at the last read, to tell what came since: none at the first.
  const counts = useRef<Map<string, number> | null>(null);
  const title = (n: News) => {
    const teams = n.teams?.filter(Boolean);
    return teams?.length === 2 ? t('matchTitle', { one: teams[0], two: teams[1] }) : n.name;
  };
  useEffect(() => {
    void fetch('/current')
      .then((r) => r.json() as Promise<{ name: string | null }>)
      .then((r) => setCurrent(r.name))
      .catch(() => undefined);
    const read = async () => {
      try {
        const found = (await (await fetch('/app/reports')).json()) as News[];
        if (!Array.isArray(found)) {
          return;
        }
        const before = counts.current;
        counts.current = new Map(found.map((n) => [n.name, n.count]));
        setNews(found);
        const more = before ? found.filter((n) => n.count > (before.get(n.name) ?? 0)) : [];
        if (more.length && 'Notification' in window && Notification.permission === 'granted') {
          const shown = new Notification(t('newReports.count', { count: more.reduce((sum, n) => sum + n.count - (before?.get(n.name) ?? 0), 0) }), {
            body: more.map(title).join(' · '),
            tag: 'reports',
          });
          shown.onclick = () => window.focus();
        }
      } catch {
        // The next read tries again.
      }
    };
    void read();
    const timer = setInterval(() => void read(), EVERY_MS);
    return () => clearInterval(timer);
  }, []);
  const go = async (name: string) => {
    if ('Notification' in window && Notification.permission === 'default') {
      void Notification.requestPermission();
    }
    if (!(await mayLeave())) {
      return;
    }
    setGoing(name);
    setError(null);
    if (name === current) {
      location.reload();
      return;
    }
    try {
      await openMatch(name);
    } catch (e) {
      setError(explain(t, (e as Error).message, 'matches.openFailed'));
      setGoing(null);
    }
  };

  return (
    news.length > 0 && (
      <Alert>
        <Flag aria-hidden className="text-primary" />
        <AlertDescription className="grid gap-2">
          {news.map((n) => (
            <div key={n.name} className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="min-w-0">
                {t('newReports.count', { count: n.count })}
                {n.name !== current && <span className="text-muted-foreground">{` · ${title(n)}`}</span>}
              </span>
              <Button size="sm" variant="outline" className="ml-auto" busy={going === n.name} disabled={going !== null} onClick={() => void go(n.name)}>
                {n.name === current ? <RefreshCw aria-hidden /> : <FolderOpen aria-hidden />}
                {t(n.name === current ? 'newReports.show' : 'newReports.open')}
              </Button>
            </div>
          ))}
          {error && <ErrorNote {...error} />}
        </AlertDescription>
      </Alert>
    )
  );
}
