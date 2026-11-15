import { useRef, useState, useSyncExternalStore, type ComponentProps, type ReactElement, type ReactNode } from 'react';
import { Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Slot } from 'radix-ui';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

const onFullscreen = (change: () => void) => {
  document.addEventListener('fullscreenchange', change);
  return () => document.removeEventListener('fullscreenchange', change);
};

/** The app's one tooltip: `label` over `children`, inside the full-screen element while there is one (the page around it is
 * hidden then). No label, no tooltip. Props and ref from a wrapping `asChild` reach `children`. With `tap`, a click or a tap
 * opens it too (a touch screen has no hover), a second tap closes it: for a trigger whose click does nothing else. */
export function Tip({
  label,
  side = 'top',
  tap = false,
  children,
  ...slot
}: { label?: ReactNode; side?: 'top' | 'right' | 'bottom' | 'left'; tap?: boolean; children: ReactElement } & Omit<ComponentProps<typeof TooltipTrigger>, 'children'>) {
  const full = useSyncExternalStore(
    onFullscreen,
    () => document.fullscreenElement,
    () => null,
  );
  const [open, setOpen] = useState(false);
  // Radix closes the tip on a press and on a click; a touch on an open tip closes it, a mouse click keeps it open.
  const closes = useRef(false);
  if (!label) {
    return <Slot.Root {...slot}>{children}</Slot.Root>;
  }
  const taps: Omit<ComponentProps<typeof TooltipTrigger>, 'children'> = tap
    ? {
        onPointerDown: (e) => {
          closes.current = open && e.pointerType !== 'mouse';
        },
        onClick: (e) => {
          e.preventDefault();
          setOpen(!closes.current);
          closes.current = false;
        },
      }
    : {};
  return (
    <Tooltip {...(tap && { open, onOpenChange: setOpen })}>
      <TooltipTrigger asChild {...slot} {...taps}>
        {children}
      </TooltipTrigger>
      <TooltipContent side={side} sideOffset={4} container={full}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

/** An explanation behind an info icon: shown on hover, focus or a tap. */
export function Hint({ label, className }: { label: ReactNode; className?: string }) {
  const { t } = useTranslation();
  return (
    <Tip label={label} tap>
      <button
        type="button"
        aria-label={t('hint')}
        className={cn(
          'relative inline-flex shrink-0 cursor-help rounded-full align-middle text-muted-foreground outline-none after:absolute after:-inset-2 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50',
          className,
        )}
      >
        <Info aria-hidden className="size-3.5" />
      </button>
    </Tip>
  );
}
