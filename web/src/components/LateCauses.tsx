import { useTranslation } from 'react-i18next';
import { changesLines, type PageChange } from '@/lib/hostedChanges';

/** Why the online page is late, one cause a line (`changesLines`), its details below it; nothing when none is known. */
export function LateCauses({ changes }: { changes: PageChange[] | null | undefined }) {
  const { t } = useTranslation();
  const causes = changesLines(changes, t);
  return causes ? (
    <ul className="list-disc space-y-0.5 pl-4">
      {causes.map((cause) => (
        <li key={cause.text}>
          {cause.text}
          {cause.details && (
            <ul className="list-disc space-y-0.5 pl-4">
              {cause.details.map((detail) => (
                <li key={detail}>{detail}</li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  ) : null;
}
