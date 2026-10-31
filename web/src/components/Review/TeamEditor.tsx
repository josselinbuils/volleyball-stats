import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { teams, type Group } from '@/lib/match';
import { post } from '@/lib/review';

/** A team's name and colour, saved to teams.json; the pages are rebuilt with them, then reloaded. */
export function TeamEditor({ g, onError }: { g: Group; onError: () => void }) {
  const { t } = useTranslation();
  const team = teams?.[g - 1];
  const [name, setName] = useState(team?.name ?? '');
  const [colour, setColour] = useState(team?.colour ?? '#000000');
  const [saving, setSaving] = useState(false);
  if (!team) {
    return null;
  }
  const changed = name.trim() !== (team.name ?? '') || colour !== team.colour;
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      await post('team', { team: g, name: name.trim() || null, colour });
      location.reload();
    } catch {
      setSaving(false);
      onError();
    }
  };

  return (
    <form onSubmit={(event) => void save(event)} className="flex flex-wrap items-center gap-2">
      <input
        type="color"
        value={colour}
        onChange={(event) => setColour(event.target.value)}
        aria-label={t('review.teamColour')}
        title={t('review.teamColour')}
        className="h-8 w-10 cursor-pointer rounded-md border border-input bg-card p-0.5"
      />
      <input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder={t('team', { n: g })}
        aria-label={t('review.teamName')}
        className="h-8 w-52 max-w-full rounded-md border border-input bg-card px-2 text-lg font-semibold shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      />
      {changed && (
        <Button type="submit" size="sm" disabled={saving}>
          {t(saving ? 'review.saving' : 'review.saveTeam')}
        </Button>
      )}
    </form>
  );
}
