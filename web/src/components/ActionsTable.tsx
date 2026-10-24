import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { SetBadge } from '@/components/SetBadge';
import { Swatch } from '@/components/Swatch';
import { useFormat } from '@/lib/format';
import { color, GROUPS, groupName, hasTeams, match, teamColor, TYPES, type Contact } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { useSet } from '@/lib/sets';

// The first and last cells of each row keep the content off the row's edges.
const FIRST = 'pl-3 max-sm:pl-2';
const LAST = 'pr-3 max-sm:pr-2';

export function ActionsTable() {
  const { t } = useTranslation();
  const { set, contacts } = useSet();
  const rows = TYPES.map((type) => ({ id: type, label: (tr: TFunction) => tr(`types.${type}`), of: contacts.filter((c) => c.type === type) }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('actions')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>{t(hasTeams ? 'actionsCaption' : 'actionsCaptionSides')}</CardDescription>
      </CardHeader>
      <CardContent>
        <Table className="max-w-2xl tabular-nums">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className={cn(FIRST, 'text-muted-foreground')}>{t('action')}</TableHead>
              {GROUPS.map((g) => (
                <TableHead key={g} className="text-right whitespace-normal text-muted-foreground max-sm:px-1 max-sm:leading-tight">
                  <span className="inline-flex items-center gap-2 [overflow-wrap:anywhere]">
                    <Swatch color={teamColor(g)} className="max-sm:hidden" />
                    {groupName(t, g)}
                  </span>
                </TableHead>
              ))}
              <TableHead className={cn(LAST, 'text-right text-muted-foreground max-sm:pl-1')}>{t('total')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map(({ id, label, of }) => (
              <TableRow key={id}>
                <TableCell className={cn(FIRST, 'whitespace-normal')}>
                  <span className="inline-flex items-center gap-2">
                    <Swatch color={color(id)} />
                    {label(t)}
                  </span>
                </TableCell>
                <Counts id={`${set}:${id}`} label={label} of={of} />
              </TableRow>
            ))}
          </TableBody>
          <TableFooter className="bg-transparent">
            <TableRow className="hover:bg-transparent">
              <TableCell className={cn(FIRST, 'font-semibold whitespace-normal')}>{t('allTouches')}</TableCell>
              <Counts id={`${set}:all`} label={(tr) => tr('allTouches')} of={contacts} />
            </TableRow>
          </TableFooter>
        </Table>
      </CardContent>
    </Card>
  );
}

function Counts({ id, label, of }: { id: string; label: (t: TFunction) => string; of: Contact[] }) {
  return (
    <>
      {GROUPS.map((g) => (
        <Count key={g} id={`${id}:${g}`} title={(t) => `${label(t)}, ${groupName(t, g)}`} picked={of.filter((c) => c.g === g)} />
      ))}
      <Count id={id} title={label} picked={of} last />
    </>
  );
}

function Count({ id, title, picked, last = false }: { id: string; title: (t: TFunction) => string; picked: Contact[]; last?: boolean }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play } = usePlayer();

  if (!picked.length) {
    return (
      <TableCell className={cn('text-right max-sm:pl-1', last ? LAST : 'pr-0')}>
        <span className="inline-block min-w-12 text-center text-muted-foreground max-sm:min-w-10" aria-label="0">
          –
        </span>
      </TableCell>
    );
  }
  const on = playlist?.key === id;
  return (
    <TableCell className={cn('py-1.5 text-right max-sm:pl-1', last ? LAST : 'pr-0')}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            aria-pressed={on}
            aria-label={`${f.num(picked.length)} · ${title(t)} · ${t('watchN', { count: picked.length })}`}
            className={cn(
              'min-w-12 text-base font-semibold max-sm:min-w-10',
              on ? 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground' : 'bg-primary/10 text-link hover:bg-primary hover:text-primary-foreground',
            )}
            onClick={() => play(title, contactClips(picked, match.duration), 0, id)}
          >
            {f.num(picked.length)}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{t('watchN', { count: picked.length })}</TooltipContent>
      </Tooltip>
    </TableCell>
  );
}
