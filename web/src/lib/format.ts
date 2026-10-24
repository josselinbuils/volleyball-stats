import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

/** m:ss, or h:mm:ss past an hour. */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor(s / 60) % 60;
  const sec = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

function formatters(lang: string) {
  const int = new Intl.NumberFormat(lang, { maximumFractionDigits: 0 });
  const dec = new Intl.NumberFormat(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const pct = new Intl.NumberFormat(lang, { style: 'percent' });
  return {
    num: (x: number) => int.format(x),
    dec: (x: number) => dec.format(x),
    pct: (x: number) => pct.format(x),
    // The SI symbol reads the same in every language.
    secs: (x: number) => `${dec.format(x)}\u00a0s`,
  };
}

export type Format = ReturnType<typeof formatters>;

/** Number formatters for the current language. */
export function useFormat(): Format {
  const { i18n } = useTranslation();
  return useMemo(() => formatters(i18n.language), [i18n.language]);
}
