import { useState } from 'react';
import { Play, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Court, Legend } from '@/components/Court';
import { SetBadge } from '@/components/SetBadge';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { color, contacts as all, GROUPS, groupName, hasTeams, match, placed, rallies, teamColor, teamRing, TYPES, type ActionType, type Contact, type Group } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { useSet } from '@/lib/sets';
import { Arrows } from '@/components/CourtChart/Arrows';
import { ContactDots } from '@/components/CourtChart/ContactDots';
import { arrows as toArrows } from '@/components/CourtChart/helpers/arrows';
import { onOwnHalf } from '@/components/CourtChart/helpers/halves';
import { ZoneGrid } from '@/components/CourtChart/ZoneGrid';

const VIEWS = ['contacts', 'zones', 'directions'] as const;
type View = (typeof VIEWS)[number];

// Each team on the half it played at the first rally: team 1 on the left.
const mirrored = hasTeams && rallies.some((r) => r.flipped);
const home = hasTeams ? onOwnHalf(all, rallies) : all;

/** The filtered touches on a top view of the court, one view at a time. */
export function CourtChart() {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const { contacts } = useSet();
  const [view, setView] = useState<View>('contacts');
  const [type, setType] = useState<ActionType | 'all'>('all');
  const [group, setGroup] = useState<Group | 'both'>('both');

  const present = TYPES.filter((p) => contacts.some((c) => c.type === p));
  const picked = contacts.filter((c) => (type === 'all' || c.type === type) && (group === 'both' || c.g === group)).map((c) => home[c.i]);
  const arrows = view === 'directions' ? toArrows(picked, home) : [];
  const shown = view === 'directions' ? arrows.map((a) => a.from) : picked.filter(placed);
  const title = (tr: TFunction) => [tr(`views.${view}`), type !== 'all' && tr(`types.${type}`), group !== 'both' && groupName(tr, group)].filter(Boolean).join(', ');
  const describe = (c: Contact) => `${t(`types.${c.type}`)}, ${groupName(t, c.g)} · ${t('rallyLower', { n: c.rally + 1 })} · ${clock(c.t)}`;
  const playFrom = (c: Contact) => play(title, contactClips(shown, match.duration), shown.indexOf(c as (typeof shown)[number]));
  const filtered = type !== 'all' || group !== 'both';

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">
            {t('court')}
            <SetBadge />
          </h2>
        </CardTitle>
        <CardDescription>
          {t(`captions.${view}`)}
          {mirrored && ` ${t('mirrored')}`}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <ToggleGroup
            type="single"
            variant="outline"
            spacing={0}
            value={view}
            onValueChange={(v) => {
              if (v) {
                setView(v as View);
              }
            }}
            aria-label={t('viewsLabel')}
            className="w-full items-stretch bg-card sm:w-auto"
          >
            {VIEWS.map((v) => (
              <ToggleGroupItem key={v} value={v} className="h-auto min-h-8 flex-1 py-1.5 leading-tight whitespace-normal data-[state=on]:bg-primary data-[state=on]:text-primary-foreground sm:flex-none">
                {t(`views.${v}`)}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <div className="grid w-full grid-cols-2 gap-3 sm:flex sm:w-auto">
            <Select value={type} onValueChange={(v) => setType(v as ActionType | 'all')}>
              <SelectTrigger aria-label={t('typeFilter')} className="w-full bg-card sm:w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('allActions')}</SelectItem>
                {present.map((p) => (
                  <SelectItem key={p} value={p}>
                    {t(`types.${p}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={String(group)} onValueChange={(v) => setGroup(v === 'both' ? v : (Number(v) as Group))}>
              <SelectTrigger aria-label={t(hasTeams ? 'teamFilter' : 'sideFilter')} className="w-full bg-card sm:w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="both">{t(hasTeams ? 'bothTeams' : 'bothSides')}</SelectItem>
                {GROUPS.map((g) => (
                  <SelectItem key={g} value={String(g)}>
                    {groupName(t, g)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {filtered && (
            <Button
              variant="ghost"
              onClick={() => {
                setType('all');
                setGroup('both');
              }}
            >
              <RotateCcw aria-hidden />
              {t('reset')}
            </Button>
          )}
          {shown.length > 0 && (
            <Button className="lg:ml-auto" onClick={() => play(title, contactClips(shown, match.duration))}>
              <Play aria-hidden className="fill-current" />
              {t('watchShown', { count: shown.length })}
            </Button>
          )}
        </div>

        <div className="relative mx-auto w-full max-w-4xl">
          <Court zones role="group" aria-label={t(`captions.${view}`)} ends={[groupName(t, 1), groupName(t, 2)]} camera={!mirrored}>
            {view === 'contacts' && <ContactDots shown={shown} describe={describe} onPlay={playFrom} />}
            {view === 'zones' && <ZoneGrid shown={shown} onPlay={(zoneTitle, inside) => play(() => zoneTitle, contactClips(inside, match.duration))} />}
            {view === 'directions' && <Arrows arrows={arrows} describe={describe} onPlay={playFrom} />}
          </Court>
          {!shown.length && (
            <p className="pointer-events-none absolute inset-x-0 top-0 bottom-6 m-0 grid place-items-center p-4">
              <span className="rounded-lg border bg-card px-3.5 py-2 text-center shadow-sm">{t(view === 'directions' ? 'emptyDirections' : 'emptyContacts')}</span>
            </p>
          )}
        </div>

        {view === 'contacts' && (
          <Legend>
            {GROUPS.filter((g) => group === 'both' || g === group).map((g) => (
              <span key={g} className="inline-flex min-w-0 items-center gap-2">
                <Swatch color={teamColor(g)} ring={teamRing(g)} />
                <span className="truncate">{groupName(t, g)}</span>
              </span>
            ))}
            <span>{t('letters')}</span>
            {present
              .filter((p) => type === 'all' || p === type)
              .map((p) => (
                <span key={p}>
                  <b className="mr-1 font-semibold text-foreground">{t(`short.${p}`)}</b>
                  {t(`types.${p}`)}
                </span>
              ))}
          </Legend>
        )}
        {view === 'directions' && (
          <Legend>
            {(['point', 'error', 'play'] as const).map((r) => (
              <span key={r} className="inline-flex items-center gap-2">
                <Swatch color={color(r)} />
                {t(`results.${r}`)}
              </span>
            ))}
          </Legend>
        )}
        <p className="text-[13px] text-muted-foreground">{t(`notes.${view}`)}</p>
      </CardContent>
    </Card>
  );
}
