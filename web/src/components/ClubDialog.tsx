import { useEffect, useState, type FormEvent } from 'react';
import { ImagePlus, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ErrorNote } from '@/components/ErrorNote';
import { Button } from '@/components/ui/button';
import { Combobox, ComboboxChip, ComboboxChips, ComboboxChipsInput, ComboboxContent, ComboboxItem, ComboboxList, ComboboxValue, useComboboxAnchor } from '@/components/ui/combobox';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import { explain, type Explained } from '@/lib/errors';
import { useRunning, reloading } from '@/hooks/useRunning';
import { clubFile, guessTeams, shrink, type ClubForm, type ClubState } from '@/components/helpers/club';

const NEW: ClubForm = { name: '', url: '', accent: '#1f6bc4', header: '#111111', logo: null, sponsors: [], teams: null };
const LOGO_PX = 256;
const SPONSOR_PX = 320;

/** A picture to pick: shown, changed or taken away. */
function PictureField({ value, label, size, onChange }: { value: string | null; label: string; size: number; onChange: (value: string | null) => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      {value && <img src={value.startsWith('data:') ? value : clubFile(value)} alt="" className="h-10 max-w-24 rounded object-contain" />}
      <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 text-sm font-medium hover:bg-muted">
        <ImagePlus aria-hidden className="size-4" />
        {value ? t('app.club.changePicture') : label}
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="sr-only"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              void shrink(file, size).then(onChange);
            }
          }}
        />
      </label>
      {value && (
        <Button type="button" variant="ghost" size="icon-sm" aria-label={t('app.club.removePicture')} onClick={() => onChange(null)}>
          <Trash2 aria-hidden />
        </Button>
      )}
    </div>
  );
}

// The item adding the name typed: it has no place among the names.
const ADD = '\u0000add:';

/** Names picked as chips among `options`, or typed: a name not there yet is added. */
function NamesField({ id, value, options, onChange }: { id: string; value: string[]; options: string[]; onChange: (value: string[]) => void }) {
  const { t } = useTranslation();
  const anchor = useComboboxAnchor();
  const [query, setQuery] = useState('');
  const typed = query.trim();
  const known = [...new Set([...options, ...value])];
  const items = typed && !known.some((name) => name.toLowerCase() === typed.toLowerCase()) ? [...known, ADD + typed] : known;
  return (
    <Combobox
      multiple
      autoHighlight
      items={items}
      value={value}
      inputValue={query}
      onInputValueChange={setQuery}
      onValueChange={(picked: string[]) => {
        onChange([...new Set(picked.map((name) => (name.startsWith(ADD) ? name.slice(ADD.length) : name)))]);
        setQuery('');
      }}
      filter={(item: string, text: string) => item.startsWith(ADD) || item.toLowerCase().includes(text.trim().toLowerCase())}
      itemToStringLabel={(item: string) => (item.startsWith(ADD) ? item.slice(ADD.length) : item)}
    >
      <ComboboxChips ref={anchor} className="min-h-9">
        <ComboboxValue>
          {(names: string[]) => (
            <>
              {names.map((name) => (
                <ComboboxChip key={name}>{name}</ComboboxChip>
              ))}
              <ComboboxChipsInput id={id} />
            </>
          )}
        </ComboboxValue>
      </ComboboxChips>
      <ComboboxContent anchor={anchor}>
        <ComboboxList>
          {(item: string) => (
            <ComboboxItem key={item} value={item}>
              {item.startsWith(ADD) ? t('app.club.addTeam', { name: item.slice(ADD.length) }) : item}
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}

/** The club, the same on the list, the review and the match pages: name, site, logo, colours, teams and the
 * sponsors on the 3D view's boards; or one of the themes to start from, or none. */
export function ClubDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  // The club as saved: null while it loads, 'failed' unread (no form then, which would replace it with an empty one).
  const [state, setState] = useState<ClubState | 'failed' | null>(null);
  const [form, setForm] = useState<ClubForm>(NEW);
  // The theme being applied, or the form being saved.
  const [saving, run] = useRunning();
  const [error, setError] = useState<Explained | null>(null);
  const load = (found: ClubState['club'], played: string[]) =>
    setForm(
      found
        ? { ...found, url: found.url ?? '', sponsors: found.sponsors.map((s) => ({ ...s, logo: s.logo ? `sponsors/${s.logo}` : null })), teams: found.teams ?? guessTeams(found.name, played) }
        : NEW,
    );
  const read = () => {
    setState(null);
    void call<ClubState>('club').then((r) => {
      if (r.ok) {
        setState(r);
        load(r.club, r.played);
      } else {
        setState('failed');
      }
    });
  };
  useEffect(read, []);
  const set = (change: Partial<ClubForm>) => setForm((f) => ({ ...f, ...change }));
  const setSponsor = (k: number, change: Partial<ClubForm['sponsors'][number]>) => set({ sponsors: form.sponsors.map((s, j) => (j === k ? { ...s, ...change } : s)) });
  const done = (key: string, path: string, body: object) =>
    run(key, async () => {
      setError(null);
      const r = await call(path, body);
      if (r.ok) {
        // The list shows the club as it now is.
        await reloading();
      }
      setError(explain(t, r.error));
    });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void done('save', 'club', {
      ...form,
      url: form.url.trim(),
      // A picture kept goes back by its file's name.
      sponsors: form.sponsors.map((s) => ({ ...s, logo: s.logo?.replace(/^sponsors\//, '') ?? null })),
    });
  };
  const ready = form.name.trim() !== '' && (!form.url.trim() || /^https?:\/\//.test(form.url.trim())) && form.sponsors.every((s) => s.name.trim());

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg"
        // The names' list opens outside the dialog: picking in it does not close it.
        onInteractOutside={(event) => {
          if ((event.target as Element | null)?.closest('[data-slot=combobox-content]')) {
            event.preventDefault();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>{t('app.club.title')}</DialogTitle>
          <DialogDescription>{t('app.club.intro')}</DialogDescription>
        </DialogHeader>
        {state === null ? (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
            {t('app.club.loading')}
          </p>
        ) : state === 'failed' ? (
          <ErrorNote
            text={t('error.loadFailed')}
            log
            action={
              <Button size="sm" variant="outline" onClick={read}>
                {t('error.retry')}
              </Button>
            }
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground">{t('app.club.from')}</span>
              {state.themes.map((p) => (
                <Button key={p.id} size="sm" variant="outline" busy={saving === `theme:${p.id}`} disabled={!!saving} onClick={() => void done(`theme:${p.id}`, 'club/theme', { id: p.id })}>
                  {p.name}
                </Button>
              ))}
              <Button size="sm" variant="outline" busy={saving === 'none'} disabled={!!saving} onClick={() => void done('none', 'club/theme', { id: 'none' })}>
                {t('app.club.none')}
              </Button>
            </div>
            <form onSubmit={submit} className="grid gap-4">
              <label className="grid gap-1 font-medium">
                {t('app.club.name')}
                <input required value={form.name} onChange={(e) => set({ name: e.target.value })} className={INPUT} />
              </label>
              <label className="grid gap-1 font-medium">
                {t('app.club.url')}
                <input type="url" placeholder="https://" value={form.url} onChange={(e) => set({ url: e.target.value })} className={INPUT} />
              </label>
              <div className="grid gap-1">
                <span className="font-medium">{t('app.club.logo')}</span>
                <PictureField value={form.logo} label={t('app.club.logo')} size={LOGO_PX} onChange={(logo) => set({ logo })} />
              </div>
              <div className="flex flex-wrap gap-4">
                {(['accent', 'header'] as const).map((key) => (
                  <label key={key} className="flex items-center gap-2 font-medium">
                    <input type="color" value={form[key]} onChange={(e) => set({ [key]: e.target.value })} className="h-9 w-12 cursor-pointer rounded-md border border-input bg-transparent p-1" />
                    {t(`app.club.${key}`)}
                  </label>
                ))}
              </div>
              <div className="grid gap-1">
                <label htmlFor="club-teams" className="font-medium">
                  {t('app.club.teams')}
                </label>
                <NamesField id="club-teams" value={form.teams ?? []} options={state?.played ?? []} onChange={(teams) => set({ teams })} />
              </div>
              <fieldset className="grid gap-2">
                <legend className="mb-1 font-medium">{t('app.club.sponsors')}</legend>
                {form.sponsors.map((sponsor, k) => (
                  <div key={k} className="grid gap-2 rounded-lg border border-border p-2">
                    <div className="flex gap-2">
                      <input
                        aria-label={t('app.club.sponsorName')}
                        placeholder={t('app.club.sponsorName')}
                        required
                        value={sponsor.name}
                        onChange={(e) => setSponsor(k, { name: e.target.value })}
                        className={cn(INPUT, 'min-w-0 flex-1')}
                      />
                      <input
                        type="color"
                        aria-label={t('app.club.board')}
                        value={sponsor.background}
                        onChange={(e) => setSponsor(k, { background: e.target.value })}
                        className="h-9 w-12 shrink-0 cursor-pointer rounded-md border border-input bg-transparent p-1"
                      />
                      <Button type="button" variant="ghost" size="icon" aria-label={t('app.club.removeSponsor')} onClick={() => set({ sponsors: form.sponsors.filter((_, j) => j !== k) })}>
                        <Trash2 aria-hidden />
                      </Button>
                    </div>
                    <PictureField value={sponsor.logo} label={t('app.club.sponsorLogo')} size={SPONSOR_PX} onChange={(logo) => setSponsor(k, { logo })} />
                  </div>
                ))}
                <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => set({ sponsors: [...form.sponsors, { name: '', background: '#ffffff', logo: null }] })}>
                  <Plus aria-hidden />
                  {t('app.club.addSponsor')}
                </Button>
              </fieldset>
              <Button type="submit" busy={saving === 'save'} disabled={!ready || !!saving}>
                {t('app.club.save')}
              </Button>
            </form>
          </>
        )}
        {error && <ErrorNote {...error} />}
      </DialogContent>
    </Dialog>
  );
}
