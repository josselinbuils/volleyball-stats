import { useSyncExternalStore, type ReactElement, type ReactNode } from 'react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const onFullscreen = (change: () => void) => {
  document.addEventListener('fullscreenchange', change);
  return () => document.removeEventListener('fullscreenchange', change);
};

/** The app's one tooltip: `label` over `children`, inside the full-screen element while there is one (the page around it is
 * hidden then). No label, no tooltip. */
export function Tip({ label, side = 'top', children }: { label?: ReactNode; side?: 'top' | 'right' | 'bottom' | 'left'; children: ReactElement }) {
  const full = useSyncExternalStore(onFullscreen, () => document.fullscreenElement);
  if (!label) {
    return children;
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side} sideOffset={4} container={full}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
