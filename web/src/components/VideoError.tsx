import { useEffect, useState, type RefObject } from 'react';
import { TriangleAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/** Over `video`, once it cannot load (a file gone, no network), says so in place of a black picture; gone when another
 * one loads. */
export function VideoError({ video }: { video: HTMLVideoElement | RefObject<HTMLVideoElement | null> | null }) {
  const { t } = useTranslation();
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const element = video && 'current' in video ? video.current : video;
    if (!element) {
      return;
    }
    // An aborted load (another source set) is no failure.
    const check = () => setFailed(!!element.error && element.error.code !== MediaError.MEDIA_ERR_ABORTED);
    check();
    const events = ['error', 'loadstart', 'emptied'];
    events.forEach((e) => element.addEventListener(e, check));
    return () => events.forEach((e) => element.removeEventListener(e, check));
  }, [video]);
  if (!failed) {
    return null;
  }
  return (
    <div role="alert" className="pointer-events-none absolute inset-0 grid place-items-center p-4">
      <p className="m-0 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1.5 text-sm text-white backdrop-blur-sm">
        <TriangleAlert aria-hidden className="size-4 shrink-0" />
        {t('error.video')}
      </p>
    </div>
  );
}
