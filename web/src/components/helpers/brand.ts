/** The club's branding as the app edits it (branding.py): a picture is a data: URL when new, its file's path when kept. */
export interface BrandForm {
  name: string;
  url: string;
  accent: string;
  header: string;
  logo: string | null;
  sponsors: { name: string; background: string; logo: string | null }[];
  /** The club's teams, null until picked. */
  teams: string[] | null;
}

export interface BrandState {
  brand: (Omit<BrandForm, 'url'> & { url: string | null }) | null;
  presets: { id: string; name: string }[];
  /** The teams of the matches, most matches first. */
  played: string[];
}

/** A picture of the club's branding, by its path in its folder. */
export function brandFile(path: string): string {
  return `/app/brand/file?path=${encodeURIComponent(path)}`;
}

/** The size a picture `width` x `height` is sent at: no taller than `px`, never enlarged. */
export function fitted(width: number, height: number, px: number): [number, number] {
  const scale = Math.min(1, px / height);
  return [Math.max(1, Math.round(width * scale)), Math.max(1, Math.round(height * scale))];
}

/** A picture file as a WebP data: URL no taller than `px`, transparency kept: light enough to send. */
export async function shrink(file: File, px: number): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const [width, height] = fitted(bitmap.width, bitmap.height, px);
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, width, height);
  return canvas.toDataURL('image/webp', 0.92);
}

const firstWord = (text: string) =>
  text
    .normalize('NFD')
    .replace(/\p{Mn}/gu, '')
    .toLowerCase()
    .split(/\s+/)[0];

/** The `played` teams named like the club `club` (ASPOM 2 for ASPOM Bègles): a first guess of its teams. */
export function guessTeams(club: string, played: string[]): string[] {
  const word = firstWord(club.trim());
  return word ? played.filter((team) => firstWord(team.trim()) === word) : [];
}
