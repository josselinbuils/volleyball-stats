import { useEffect } from 'react';

/** `report` given `value` (plain data) each time it changes, compared as JSON: a copy, never the render's own. */
export function useReported<T>(value: T, report?: (value: T) => void) {
  const json = JSON.stringify(value);
  useEffect(() => {
    report?.(JSON.parse(json) as T);
  }, [json]);
}
