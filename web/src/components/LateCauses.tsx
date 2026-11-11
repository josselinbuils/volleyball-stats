import { useTranslation } from 'react-i18next';
import { changesLines, type PageChange } from '@/lib/hostedChanges';

/** Why the online page is late, one cause a line (`changesLines`); nothing when none is known. */
export function LateCauses({ changes }: { changes: PageChange[] | null | undefined }) {
  const { t } = useTranslation();
  const causes = changesLines(changes, t);
  return causes ? (
    <ul className="list-disc space-y-0.5 pl-4">
      {causes.map((cause) => (
        <li key={cause}>{cause}</li>
      ))}
    </ul>
  ) : null;
}
