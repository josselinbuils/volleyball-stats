import { ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

/** The way back to the page above this one, at its top: the app's window has no back button. */
export function BackLink({ href, label, className }: { href: string; label: string; className?: string }) {
  return (
    <a
      href={href}
      className={cn(
        '-mx-1 inline-flex items-center gap-1.5 justify-self-start rounded-md px-1 text-sm font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50',
        className,
      )}
    >
      <ArrowLeft aria-hidden className="size-4 shrink-0" />
      {label}
    </a>
  );
}
