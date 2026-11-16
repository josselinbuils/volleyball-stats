import type { Rally } from '@/lib/match';

/** How long `rally` lasted in the match, whatever the video plays (the hosted one slows close calls down). */
export const lasted = (rally: Pick<Rally, 'start' | 'end' | 'real'>): number => (rally.real ? rally.real[1] - rally.real[0] : rally.end - rally.start);
