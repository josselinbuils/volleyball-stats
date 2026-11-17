import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MessageSquareText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tip } from '@/components/Tip';

/** The owner's note on a rally, behind a button (its icon) until it has text, saved on leaving the field or when the rally goes out of view. Render
 * it keyed by the rally. `onSave` tells whether it was saved: if not, the next save tries again. */
export function RallyComment({ text, onFocus, onSave }: { text: string; onFocus: () => void; onSave: (text: string) => Promise<boolean> }) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(text);
  const [adding, setAdding] = useState(false);
  const latest = useRef({ draft: text, saved: text, onSave });
  latest.current.onSave = onSave;
  const save = () => {
    const now = latest.current;
    const clean = now.draft.trim();
    if (clean !== now.saved) {
      void now.onSave(clean).then((ok) => {
        if (ok) {
          now.saved = clean;
        }
      });
    }
  };
  useEffect(() => save, []);
  if (!draft.trim() && !adding) {
    return (
      <Tip label={t('review.reportCommentAdd')}>
        <Button variant="outline" size="icon-sm" className="bg-card" aria-label={t('review.reportCommentAdd')} onClick={() => setAdding(true)}>
          <MessageSquareText aria-hidden />
        </Button>
      </Tip>
    );
  }
  return (
    <label className="grid w-full gap-1.5 text-sm">
      {t('review.reportComment')}
      <textarea
        rows={2}
        autoFocus={adding}
        value={draft}
        placeholder={t('review.reportCommentHelp')}
        className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
        onFocus={() => {
          setAdding(true);
          onFocus();
        }}
        onBlur={() => {
          save();
          setAdding(false);
        }}
        onChange={(e) => {
          latest.current.draft = e.target.value;
          setDraft(e.target.value);
        }}
      />
    </label>
  );
}
