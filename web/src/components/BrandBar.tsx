import { useTranslation } from 'react-i18next';
import { match } from '@/lib/match';

/** The club's band at the top of the page, linking to its website. */
export function BrandBar() {
  const { t } = useTranslation();
  const brand = match.brand;
  if (!brand) {
    return null;
  }
  const content = (
    <>
      {brand.logo && <img src={brand.logo} alt="" width={48} height={48} className="size-12 shrink-0 object-contain max-sm:size-10" />}
      <span className="text-lg font-bold tracking-tight max-sm:text-base">{brand.name}</span>
    </>
  );
  return (
    <div className="bg-(--brand-header) text-white">
      <div className="mx-auto flex max-w-6xl items-center px-4 py-2">
        {brand.url ? (
          <a href={brand.url} target="_blank" rel="noopener" aria-label={t('clubSite', { name: brand.name })} className="-mx-1.5 inline-flex items-center gap-3 rounded-md px-1.5 py-1 outline-none hover:underline focus-visible:ring-3 focus-visible:ring-white/70">
            {content}
          </a>
        ) : (
          <div className="inline-flex items-center gap-3">{content}</div>
        )}
      </div>
    </div>
  );
}
