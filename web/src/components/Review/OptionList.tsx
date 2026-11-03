import { useEffect, useState, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

export interface Option {
  key: string;
  label: string;
  picture?: string;
  /** Shown after the label, fainter. */
  hint?: string;
}

/** Where the list of the `field` goes while `open`: it sits over the page, under the field, and
 * follows it when anything scrolls (focusing or typing scrolls the picture strip itself). */
export function useFieldPlace(field: RefObject<HTMLInputElement | null>, open: boolean): DOMRect | null {
  const [place, setPlace] = useState<DOMRect | null>(null);
  useEffect(() => {
    if (!open) {
      return;
    }
    const follow = () => setPlace(field.current?.getBoundingClientRect() ?? null);
    follow();
    window.addEventListener('scroll', follow, true);
    window.addEventListener('resize', follow);
    return () => {
      window.removeEventListener('scroll', follow, true);
      window.removeEventListener('resize', follow);
    };
  }, [field, open]);
  return place;
}

/** The options a field's text matches, over the page at `place`, `active` highlighted. */
export function OptionList({
  id,
  label,
  place,
  options,
  active,
  onPick,
  onActive,
}: {
  id: string;
  label: string;
  place: DOMRect;
  options: Option[];
  active: number;
  onPick: (key: string) => void;
  onActive: (k: number) => void;
}) {
  const pictured = options.some((o) => o.picture);
  return createPortal(
    <ul
      id={id}
      role="listbox"
      aria-label={label}
      style={{ left: place.left, top: place.bottom + 4, minWidth: place.width }}
      className="fixed z-50 m-0 max-h-80 w-max max-w-[90vw] list-none overflow-auto rounded-md border bg-popover p-1 text-[13px] text-popover-foreground shadow-md"
    >
      {options.map((o, k) => (
        <li
          key={o.key}
          id={`${id}-${k}`}
          role="option"
          aria-selected={k === active}
          // Before the field's blur, which would close the list.
          onMouseDown={(event) => {
            event.preventDefault();
            onPick(o.key);
          }}
          onMouseEnter={() => onActive(k)}
          className={cn('flex cursor-pointer items-center gap-2 rounded px-2 py-1', k === active && 'bg-accent text-accent-foreground')}
        >
          {pictured &&
            (o.picture ? (
              <img src={o.picture} alt="" loading="lazy" className="size-8 shrink-0 rounded-sm bg-muted object-cover object-top" />
            ) : (
              <span aria-hidden className="size-8 shrink-0 rounded-sm bg-muted" />
            ))}
          {o.label}
          {o.hint && <span className="text-muted-foreground">{o.hint}</span>}
        </li>
      ))}
    </ul>,
    // In full screen, only the full-screen block shows.
    document.fullscreenElement ?? document.body,
  );
}
