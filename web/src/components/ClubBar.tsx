import { useTranslation } from 'react-i18next';
import { Settings } from '@/components/Settings';
import { Tip } from '@/components/Tip';
import type { Club } from '@/lib/match';

/** The club's band at the top of the page, linking to its website, and on the right the theme and language when
 * `settings`, and the project's repository. */
export function ClubBar({ club, settings = false }: { club: Club | null; settings?: boolean }) {
  const { t } = useTranslation();
  if (!club) {
    return null;
  }
  const content = (
    <>
      {club.logo && <img src={club.logo} alt="" width={48} height={48} className="size-12 shrink-0 object-contain max-sm:size-10" />}
      <span className="text-lg font-bold tracking-tight max-sm:text-base">{club.name}</span>
    </>
  );
  return (
    <div className="bg-(--brand-header) text-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-2">
        {club.url ? (
          <a
            href={club.url}
            target="_blank"
            rel="noopener"
            aria-label={t('clubSite', { name: club.name })}
            className="-mx-1.5 inline-flex items-center gap-3 rounded-md px-1.5 py-1 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-white/70"
          >
            {content}
          </a>
        ) : (
          <div className="inline-flex items-center gap-3">{content}</div>
        )}
        <div className="flex shrink-0 items-center gap-1">
          {settings && <Settings onBar />}
          <Tip label={t('sourceCode')}>
            <a
              href="https://github.com/josselinbuils/volleyball-stats"
              target="_blank"
              rel="noopener"
              aria-label={t('sourceCode')}
              className="-mr-1.5 shrink-0 rounded-md p-1.5 outline-none max-sm:p-2 hover:bg-white/15 focus-visible:ring-3 focus-visible:ring-white/70"
            >
              {/* GitHub's mark, from Primer Octicons (mark-github-16). */}
              <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden className="size-6 max-sm:size-5">
                <path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z" />
              </svg>
            </a>
          </Tip>
        </div>
      </div>
    </div>
  );
}
