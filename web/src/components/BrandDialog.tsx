import { useEffect, useState, type FormEvent } from 'react';
import { ImagePlus, Plus, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { INPUT, call } from '@/lib/app';
import { brandFile, guessTeams, shrink, type BrandForm, type BrandState } from '@/components/helpers/brand';

const NEW: BrandForm = { name: '', url: '', accent: '#1f6bc4', header: '#111111', logo: null, sponsors: [], teams: null };
const LOGO_PX = 256;
const SPONSOR_PX = 320;

/** A picture to pick: shown, changed or taken away. */
function PictureField({ value, label, size, onChange }: { value: string | null; label: string; size: number; onChange: (value: string | null) => void }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      {value && <img src={value.startsWith('data:') ? value : brandFile(value)} alt="" className="h-10 max-w-24 rounded object-contain" />}
      <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-background px-2.5 text-sm font-medium hover:bg-muted">
        <ImagePlus aria-hidden className="size-4" />
        {value ? t('app.brand.changePicture') : label}
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
        <Button type="button" variant="ghost" size="icon-sm" aria-label={t('app.brand.removePicture')} onClick={() => onChange(null)}>
          <Trash2 aria-hidden />
        </Button>
      )}
    </div>
  );
}

/** The club's branding, the same on the list, the review and the match pages: name, site, logo, colours and the
 * sponsors on the 3D view's boards; or one of the themes to start from, or none. */
export function BrandDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const [state, setState] = useState<BrandState | null>(null);
  const [form, setForm] = useState<BrandForm>(NEW);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(false);
  const load = (found: BrandState['brand'], played: string[]) =>
    setForm(
      found
        ? { ...found, url: found.url ?? '', sponsors: found.sponsors.map((s) => ({ ...s, logo: s.logo ? `sponsors/${s.logo}` : null })), teams: found.teams ?? guessTeams(found.name, played) }
        : NEW,
    );
  useEffect(() => {
    void call<BrandState>('brand').then((r) => {
      if (r.ok) {
        setState(r);
        load(r.brand, r.played);
      }
    });
  }, []);
  const teams = [...new Set([...(state?.played ?? []), ...(form.teams ?? [])])];
  const picked = form.teams ?? [];
  const set = (change: Partial<BrandForm>) => setForm((f) => ({ ...f, ...change }));
  const setSponsor = (k: number, change: Partial<BrandForm['sponsors'][number]>) => set({ sponsors: form.sponsors.map((s, j) => (j === k ? { ...s, ...change } : s)) });
  const done = async (path: string, body: object) => {
    setSaving(true);
    setError(false);
    const r = await call(path, body);
    setSaving(false);
    if (r.ok) {
      // The list shows the new branding.
      location.reload();
    } else {
      setError(true);
    }
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void done('brand', {
      ...form,
      url: form.url.trim(),
      // A picture kept goes back by its file's name.
      sponsors: form.sponsors.map((s) => ({ ...s, logo: s.logo?.replace(/^sponsors\//, '') ?? null })),
    });
  };
  const ready = form.name.trim() !== '' && (!form.url.trim() || /^https?:\/\//.test(form.url.trim())) && form.sponsors.every((s) => s.name.trim());

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('app.brand.title')}</DialogTitle>
          <DialogDescription>{t('app.brand.intro')}</DialogDescription>
        </DialogHeader>
        {state && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">{t('app.brand.from')}</span>
            {state.presets.map((p) => (
              <Button key={p.id} size="sm" variant="outline" disabled={saving} onClick={() => void done('brand/preset', { id: p.id })}>
                {p.name}
              </Button>
            ))}
            <Button size="sm" variant="outline" disabled={saving} onClick={() => void done('brand/preset', { id: 'none' })}>
              {t('app.brand.none')}
            </Button>
          </div>
        )}
        <form onSubmit={submit} className="grid gap-4">
          <label className="grid gap-1 font-medium">
            {t('app.brand.name')}
            <input required value={form.name} onChange={(e) => set({ name: e.target.value })} className={INPUT} />
          </label>
          <label className="grid gap-1 font-medium">
            {t('app.brand.url')}
            <input type="url" placeholder="https://" value={form.url} onChange={(e) => set({ url: e.target.value })} className={INPUT} />
          </label>
          <div className="grid gap-1">
            <span className="font-medium">{t('app.brand.logo')}</span>
            <PictureField value={form.logo} label={t('app.brand.logo')} size={LOGO_PX} onChange={(logo) => set({ logo })} />
          </div>
          <div className="flex flex-wrap gap-4">
            {(['accent', 'header'] as const).map((key) => (
              <label key={key} className="flex items-center gap-2 font-medium">
                <input type="color" value={form[key]} onChange={(e) => set({ [key]: e.target.value })} className="h-9 w-12 cursor-pointer rounded-md border border-input bg-transparent p-1" />
                {t(`app.brand.${key}`)}
              </label>
            ))}
          </div>
          {teams.length > 0 && (
            <fieldset className="grid gap-2">
              <legend className="mb-1 font-medium">{t('app.brand.teams')}</legend>
              <div className="flex flex-wrap gap-x-4 gap-y-2">
                {teams.map((team) => (
                  <label key={team} className="flex items-center gap-2">
                    <input type="checkbox" checked={picked.includes(team)} onChange={(e) => set({ teams: e.target.checked ? [...picked, team] : picked.filter((p) => p !== team) })} />
                    {team}
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          <fieldset className="grid gap-2">
            <legend className="mb-1 font-medium">{t('app.brand.sponsors')}</legend>
            {form.sponsors.map((sponsor, k) => (
              <div key={k} className="grid gap-2 rounded-lg border border-border p-2">
                <div className="flex gap-2">
                  <input
                    aria-label={t('app.brand.sponsorName')}
                    placeholder={t('app.brand.sponsorName')}
                    required
                    value={sponsor.name}
                    onChange={(e) => setSponsor(k, { name: e.target.value })}
                    className={cn(INPUT, 'min-w-0 flex-1')}
                  />
                  <input
                    type="color"
                    aria-label={t('app.brand.board')}
                    value={sponsor.background}
                    onChange={(e) => setSponsor(k, { background: e.target.value })}
                    className="h-9 w-12 shrink-0 cursor-pointer rounded-md border border-input bg-transparent p-1"
                  />
                  <Button type="button" variant="ghost" size="icon" aria-label={t('app.brand.removeSponsor')} onClick={() => set({ sponsors: form.sponsors.filter((_, j) => j !== k) })}>
                    <Trash2 aria-hidden />
                  </Button>
                </div>
                <PictureField value={sponsor.logo} label={t('app.brand.sponsorLogo')} size={SPONSOR_PX} onChange={(logo) => setSponsor(k, { logo })} />
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => set({ sponsors: [...form.sponsors, { name: '', background: '#ffffff', logo: null }] })}>
              <Plus aria-hidden />
              {t('app.brand.addSponsor')}
            </Button>
          </fieldset>
          <Button type="submit" disabled={!ready || saving}>
            {t('app.brand.save')}
          </Button>
        </form>
        {error && (
          <p role="alert" className="text-destructive">
            {t('review.error')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
