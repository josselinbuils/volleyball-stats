import { useSyncExternalStore } from 'react';

/** Phones: narrower than Tailwind's `sm`. */
export const PHONE = '(max-width: 639px)';

export const isPhone = () => matchMedia(PHONE).matches;

/** Whether the screen is a phone's width, re-rendering when it changes. */
export function usePhone(): boolean {
  return useSyncExternalStore((listener) => {
    const query = matchMedia(PHONE);
    query.addEventListener('change', listener);
    return () => query.removeEventListener('change', listener);
  }, isPhone);
}
