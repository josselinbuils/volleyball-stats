import { useState } from 'react';
import { Play, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Court, Legend } from '@/components/Court';
import { Swatch } from '@/components/Swatch';
import { clock } from '@/lib/format';
import { color, contacts, match, placed, present, SIDES, type ActionType, type Contact, type Side } from '@/lib/match';
import { usePlayer } from '@/lib/player';
import { contactClips } from '@/lib/playlist';
import { Arrows } from '@/components/CourtChart/Arrows';
import { ContactDots } from '@/components/CourtChart/ContactDots';
import { arrows as toArrows } from '@/components/CourtChart/helpers/arrows';
import { ZoneGrid } from '@/components/CourtChart/ZoneGrid';

const VIEWS = ['contacts', 'zones', 'directions'] as const;
type View = (typeof VIEWS)[number];

/** The filtered touches on a top view of the court, one view at a time. */
export function CourtChart() {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const [view, setView] = useState<View>('contacts');
  const [type, setType] = useState<ActionType | 'all'>('all');
  const [side, setSide] = useState<Side | 'both'>('both');

  const picked = contacts.filter((c) => (type === 'all' || c.type === type) && (side === 'both' || c.side === side));
  const arrows = view === 'directions' ? toArrows(picked, contacts) : [];
  const shown = view === 'directions' ? arrows.map((a) => a.from) : picked.filter(placed);
  const title = (tr: TFunction) => [tr(`views.${view}`), type !== 'all' && tr(`types.${type}`), side !== 'both' && tr(`${side}Side`).toLowerCase()].filter(Boolean).join(', ');
  const describe = (c: Contact) => `${t(`types.${c.type}`)}, ${t(`${c.side}Side`).toLowerCase()} · ${t('rallyLower', { n: c.rally + 1 })} · ${clock(c.t)}`;
  const playFrom = (c: Contact) => play(title, contactClips(shown, match.duration), shown.indexOf(c as (typeof shown)[number]));
  const filtered = type !== 'all' || side !== 'both';

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{t('court')}</h2>
        </CardTitle>
        <CardDescription>{t(`captions.${view}`)}</CardDescription>
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
            <Select value={side} onValueChange={(v) => setSide(v as Side | 'both')}>
              <SelectTrigger aria-label={t('sideFilter')} className="w-full bg-card sm:w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="both">{t('bothSides')}</SelectItem>
                {SIDES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {t(`${s}Side`)}
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
                setSide('both');
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
          <Court zones role="group" aria-label={t(`captions.${view}`)}>
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
            {present
              .filter((p) => type === 'all' || p === type)
              .map((p) => (
                <span key={p} className="inline-flex items-center gap-2">
                  <Swatch color={color(p)} />
                  {`${t(`short.${p}`)} · ${t(`types.${p}`)}`}
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
