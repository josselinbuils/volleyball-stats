import { useState } from 'react';
import { Columns2, PanelsTopLeft, PictureInPicture2, RectangleHorizontal } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { VideoButton } from '@/components/VideoButton';

/** What full screen shows: the video alone, the court's replay beside it, or the replay in its corner. */
export const LAYOUTS = { video: RectangleHorizontal, side: Columns2, inset: PictureInPicture2 } as const;
export type Layout = keyof typeof LAYOUTS;
const KEY = 'fullLayout';

/** The full-screen layout, kept in this browser. */
export function useLayout(): [Layout, (next: Layout) => void] {
  const [layout, setLayout] = useState<Layout>(() => {
    try {
      const saved = localStorage.getItem(KEY);
      return saved && saved in LAYOUTS ? (saved as Layout) : 'video';
    } catch {
      return 'video';
    }
  });
  const choose = (next: Layout) => {
    setLayout(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // Kept for this page only.
    }
  };
  return [layout, choose];
}

/** The video bar's menu picking the full-screen layout. */
export function LayoutMenu({ layout, onLayout, className }: { layout: Layout; onLayout: (next: Layout) => void; className?: string }) {
  const { t } = useTranslation();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <VideoButton label={t('fullLayout.label')} className={className}>
          <PanelsTopLeft aria-hidden />
        </VideoButton>
      </DropdownMenuTrigger>
      {/* Inside the full-screen element: the page around it is hidden. */}
      <DropdownMenuContent side="top" container={document.fullscreenElement}>
        {(Object.entries(LAYOUTS) as [Layout, (typeof LAYOUTS)[Layout]][]).map(([value, Icon]) => (
          <DropdownMenuCheckboxItem key={value} checked={layout === value} onCheckedChange={() => onLayout(value)}>
            <Icon aria-hidden />
            {t(`fullLayout.${value}`)}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
