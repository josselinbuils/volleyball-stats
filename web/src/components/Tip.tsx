import { useSyncExternalStore, type ComponentProps, type ReactElement, type ReactNode } from 'react';
import { Slot } from 'radix-ui';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const onFullscreen = (change: () => void) => {
  document.addEventListener('fullscreenchange', change);
  return () => document.removeEventListener('fullscreenchange', change);
};

/** The app's one tooltip: `label` over `children`, inside the full-screen element while there is one (the page around it is
 * hidden then). No label, no tooltip. Props and ref from a wrapping `asChild` reach `children`. */
export function Tip({
  label,
  side = 'top',
  children,
  ...slot
}: { label?: ReactNode; side?: 'top' | 'right' | 'bottom' | 'left'; children: ReactElement } & Omit<ComponentProps<typeof TooltipTrigger>, 'children'>) {
  const full = useSyncExternalStore(
    onFullscreen,
    () => document.fullscreenElement,
    () => null,
  );
  if (!label) {
    return <Slot.Root {...slot}>{children}</Slot.Root>;
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild {...slot}>
        {children}
      </TooltipTrigger>
      <TooltipContent side={side} sideOffset={4} container={full}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
