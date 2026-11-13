import { useEffect, useState } from 'react';
import { match } from '@/lib/match';
import { readPhotos, review } from '@/lib/review';

// How often the review asks whether the new card pictures are made: about 45 s after an apply on a 2-hour match.
const EVERY_MS = 3000;

/** The cards' pictures: `pending` while they are out of date (an apply came since), the new ones put in `match.people`
 * and `review.photos` once made, `error` why they failed (`network` when the server did not answer). */
export function usePhotos(): { pending: boolean; error: string | null } {
  const [state, setState] = useState({ pending: review?.photosPending ?? false, error: review?.photosError ?? null });
  useEffect(() => {
    if (!state.pending) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const found = await readPhotos();
        if (found.photosPending) {
          return;
        }
        window.clearInterval(timer);
        for (const [key, photo] of Object.entries(found.people)) {
          if (match.people[key]) {
            match.people[key].photo = photo ?? undefined;
          }
        }
        if (review) {
          review.photos = found.photos ?? review.photos;
          review.photosPending = false;
        }
        setState({ pending: false, error: found.photosError ?? null });
      } catch {
        window.clearInterval(timer);
        setState({ pending: false, error: 'network' });
      }
    }, EVERY_MS);
    return () => window.clearInterval(timer);
  }, [state.pending]);
  return state;
}
