import { useEffect, useLayoutEffect, useRef, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { SetFilter } from '@/components/Header/SetFilter';
import { match } from '@/lib/match';
import { cn } from '@/lib/utils';

// The page's sections by their ids, each a direct child of `main`.
const SECTIONS = ['story', 'stats', 'replay', 'court', 'mine', 'trophies', 'coach', 'rallies'];
// Pixels between the bar and a section brought under it.
const GAP = 12;

const sectionName = (t: TFunction, id: string) => t(`nav.${id === 'replay' ? (match.video ? 'video' : 'replay') : id}`);
const smooth = (): ScrollBehavior => (matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth');

/** The bar staying at the top of the screen while the page scrolls: the set filter and links to the sections, the one
 * on screen marked; the links scroll sideways when they do not fit. */
export function StickyBar() {
  return (
    <div className="sticky top-0 z-30 -mx-4 flex min-w-0 items-center gap-x-6 gap-y-2 bg-background/95 px-5 py-2.5 shadow-[0_1px_0_var(--border)] backdrop-blur-sm max-sm:-my-1 max-sm:flex-col max-sm:items-stretch">
      <SetFilter />
      <SectionLinks />
    </div>
  );
}

function SectionLinks() {
  const { t } = useTranslation();
  const strip = useRef<HTMLElement>(null);
  // The sections on the page in its order: some can be missing, "Mon match" comes first on a phone.
  const [ids, setIds] = useState<string[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  // The strip's sides with links out of sight, faded.
  const [hidden, setHidden] = useState({ start: false, end: false });

  useLayoutEffect(() => {
    const main = strip.current?.closest('main');
    if (!main) {
      return;
    }
    const read = () => setIds([...main.children].map((e) => e.id).filter((id) => SECTIONS.includes(id)));
    read();
    const observer = new MutationObserver(read);
    observer.observe(main, { childList: true });
    return () => observer.disconnect();
  }, []);

  // The section under the bar, the last one whose top went past it.
  useEffect(() => {
    const bar = strip.current?.parentElement;
    if (!bar) {
      return;
    }
    let frame = 0;
    const update = () => {
      frame = 0;
      const line = bar.getBoundingClientRect().bottom + GAP + 1;
      setCurrent(ids.findLast((id) => (document.getElementById(id)?.getBoundingClientRect().top ?? Infinity) <= line) ?? null);
    };
    const onScroll = () => {
      frame ||= requestAnimationFrame(update);
    };
    update();
    addEventListener('scroll', onScroll, { passive: true });
    addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(frame);
      removeEventListener('scroll', onScroll);
      removeEventListener('resize', onScroll);
    };
  }, [ids]);

  // The marked link kept in view in the strip, without moving the page.
  useEffect(() => {
    const box = strip.current;
    const link = box?.querySelector<HTMLElement>('[aria-current]');
    if (!box || !link) {
      return;
    }
    const l = link.getBoundingClientRect();
    const s = box.getBoundingClientRect();
    if (l.left < s.left || l.right > s.right) {
      box.scrollBy({ left: l.left - s.left - (s.width - l.width) / 2, behavior: smooth() });
    }
  }, [current]);

  useEffect(() => {
    const box = strip.current;
    if (!box) {
      return;
    }
    const sides = () => setHidden({ start: box.scrollLeft > 1, end: box.scrollLeft + box.clientWidth < box.scrollWidth - 1 });
    sides();
    const observer = new ResizeObserver(sides);
    observer.observe(box);
    box.addEventListener('scroll', sides, { passive: true });
    return () => {
      observer.disconnect();
      box.removeEventListener('scroll', sides);
    };
  }, [ids]);

  const go = (e: MouseEvent, id: string) => {
    const section = document.getElementById(id);
    const bar = strip.current?.parentElement;
    if (!section || !bar) {
      return;
    }
    e.preventDefault();
    scrollTo({ top: scrollY + section.getBoundingClientRect().top - bar.offsetHeight - GAP, behavior: smooth() });
  };

  const fade = (side: string) => `linear-gradient(to ${side}, transparent, #000 1.5rem)`;
  return (
    <nav
      ref={strip}
      aria-label={t('sections')}
      className="-my-1 flex min-w-0 flex-1 gap-1 overflow-x-auto py-1 [scrollbar-width:none] max-sm:-mx-5 max-sm:px-2 [&::-webkit-scrollbar]:hidden"
      style={{ maskImage: [hidden.start && fade('right'), hidden.end && fade('left')].filter(Boolean).join(', ') || undefined, maskComposite: 'intersect' }}
    >
      {ids.map((id) => (
        <a
          key={id}
          href={`#${id}`}
          aria-current={id === current ? 'location' : undefined}
          onClick={(e) => go(e, id)}
          className={cn(
            'inline-flex h-9 shrink-0 items-center rounded-md px-3 text-[15px] whitespace-nowrap text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 sm:first:ml-auto',
            'aria-[current]:bg-muted aria-[current]:font-semibold aria-[current]:text-foreground',
          )}
        >
          {sectionName(t, id)}
        </a>
      ))}
    </nav>
  );
}
