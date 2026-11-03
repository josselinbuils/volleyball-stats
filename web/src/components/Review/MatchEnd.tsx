import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { clock } from '@/lib/format';
import { review } from '@/lib/review';

const TIME = /^\d+(:[0-5]\d){1,2}$/;

/** When the match ended, typed or taken from the video (`now`): what follows is left out. */
export function MatchEnd({ now, onSave }: { now: number; onSave: (time: string) => void }) {
  const { t } = useTranslation();
  const given = review?.matchEnd ?? '';
  const [text, setText] = useState(given);
  const typed = text.trim();
  const save = (event: FormEvent) => {
    event.preventDefault();
    onSave(typed);
  };

  return (
    <form onSubmit={save} className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2 text-sm font-medium">
        {t('review.matchEnd')}
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="1:18:10"
          className="h-8 w-24 rounded-md border border-input bg-card px-2 text-sm font-normal tabular-nums shadow-xs outline-none focus-visible:border-ring"
        />
      </label>
      <Button type="button" variant="outline" size="sm" className="bg-card" onClick={() => setText(clock(now))}>
        {t('review.matchEndHere')}
      </Button>
      {typed !== given && (
        <Button type="submit" size="sm" disabled={typed !== '' && !TIME.test(typed)}>
          {t('review.saveMatchEnd')}
        </Button>
      )}
    </form>
  );
}
