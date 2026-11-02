import { useState } from 'react';
import { Clapperboard, Download } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { match, type Person } from '@/lib/match';

/** A player's film, on a page that has the video: its button among those around it, the film on a line of its own below them. */
export function Film({ person }: { person: Person }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const src = person.name ? match.films?.[person.name] : undefined;
  if (!src) {
    return null;
  }
  const file = src.split('?')[0].split('/').pop();
  return (
    <>
      {!open && (
        <Button variant="outline" onClick={() => setOpen(true)}>
          <Clapperboard aria-hidden />
          {t('myMatch.film.watch')}
        </Button>
      )}
      {open && (
        <div className="grid w-full justify-items-start gap-2">
          <video src={src} controls autoPlay playsInline className="w-56 rounded-lg bg-black" />
          <Button variant="outline" asChild>
            <a href={src} download={file}>
              <Download aria-hidden />
              {t('myMatch.film.save')}
            </a>
          </Button>
        </div>
      )}
    </>
  );
}
