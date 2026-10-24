import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { Swatch } from '@/components/Swatch';
import { useFormat } from '@/lib/format';
import { color, contacts, match, SIDES, TYPES, type Contact, type Side } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';

const sideTitle = (t: TFunction, side: Side) => t(`${side}Side`).toLowerCase();

export function ActionsTable() {
  const { t } = useTranslation();
  const rows = TYPES.map((type) => ({ id: type, label: (tr: TFunction) => tr(`types.${type}`), of: contacts.filter((c) => c.type === type) }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t('actions')}</h2>
        </CardTitle>
        <CardDescription>{t('actionsCaption')}</CardDescription>
      </CardHeader>
      <CardContent>
        <Table className="max-w-2xl tabular-nums">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-0 text-muted-foreground">{t('action')}</TableHead>
              {SIDES.map((side) => (
                <TableHead key={side} className="text-right whitespace-normal text-muted-foreground max-sm:px-1 max-sm:leading-tight">
                  <span className="inline-flex items-center gap-2">
                    <Swatch color={color(side)} className="max-sm:hidden" />
                    {t(`${side}Side`)}
                  </span>
                </TableHead>
              ))}
              <TableHead className="pr-0 text-right text-muted-foreground max-sm:pl-1">{t('total')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map(({ id, label, of }) => (
              <TableRow key={id}>
                <TableCell className="pl-0 whitespace-normal">
                  <span className="inline-flex items-center gap-2">
                    <Swatch color={color(id)} />
                    {label(t)}
                  </span>
                </TableCell>
                <Counts id={id} label={label} of={of} />
              </TableRow>
            ))}
          </TableBody>
          <TableFooter className="bg-transparent">
            <TableRow className="hover:bg-transparent">
              <TableCell className="pl-0 font-semibold whitespace-normal">{t('allTouches')}</TableCell>
              <Counts id="all" label={(tr) => tr('allTouches')} of={contacts} />
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
      {SIDES.map((side) => (
        <Count key={side} id={`${id}:${side}`} title={(t) => `${label(t)}, ${sideTitle(t, side)}`} picked={of.filter((c) => c.side === side)} />
      ))}
      <Count id={id} title={label} picked={of} />
    </>
  );
}

function Count({ id, title, picked }: { id: string; title: (t: TFunction) => string; picked: Contact[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  const { playlist, play } = usePlayer();

  if (!picked.length) {
    return (
      <TableCell className="pr-0 text-right max-sm:pl-1">
        <span className="inline-block min-w-12 text-center text-muted-foreground max-sm:min-w-10" aria-label="0">
          –
        </span>
      </TableCell>
    );
  }
  const on = playlist?.key === id;
  return (
    <TableCell className="py-1.5 pr-0 text-right max-sm:pl-1">
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
