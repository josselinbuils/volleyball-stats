import { RotateCcw, RotateCw } from 'lucide-react';

/** A circular arrow with the seconds inside it, as video players draw it: in a `relative` button. */
export function SkipIcon({ seconds }: { seconds: number }) {
  const Arrow = seconds < 0 ? RotateCcw : RotateCw;
  return (
    <>
      <Arrow aria-hidden className="size-6!" />
      <span aria-hidden className="absolute inset-0 grid place-items-center pt-px text-[8px] font-bold">
        {Math.abs(seconds)}
      </span>
    </>
  );
}
