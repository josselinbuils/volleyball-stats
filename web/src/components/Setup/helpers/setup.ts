import type { Team } from '@/lib/match';

/** A check of the machine (doctor.py): its status and the values its text shows. */
export interface Check {
  id: 'tools' | 'gpu' | 'memory' | 'disk' | 'models' | 'code' | 'busy';
  status: 'ok' | 'warn' | 'error';
  missing?: string[] | number;
  command?: string | null;
  kind?: 'cuda' | 'mps' | 'cpu' | 'driver' | 'torch';
  name?: string | null;
  gb?: number | null;
  wsl?: boolean;
  slow?: boolean;
  total?: number;
  behind?: number;
  load?: number;
  cores?: number;
  nice?: number;
  detail?: string;
}

/** A job (jobs.py) as the app shows it. */
export interface Job {
  id: string;
  kind: 'import' | 'court' | 'pipeline' | 'models' | 'videos' | 'hosting' | 'backup';
  running: boolean;
  step?: string | null;
  failed?: string;
  error?: string | null;
  progress?: number | null;
  stage?: string | null;
  started: number;
  ended?: number;
}

/** A match not ready for the review (app.preparing) and what it waits for. */
export interface Preparing {
  name: string;
  date: string | null;
  teams: Team[] | null;
  job: Job | null;
  start: boolean;
  court: boolean;
  state: 'importing' | 'court' | 'check' | 'running' | 'failed' | 'elsewhere' | 'stalled';
  /** The court being found among the known gyms; `placing`, from the clicks. */
  searching?: boolean;
  placing?: boolean;
  /** The clicks gave no court. */
  fitFailed?: boolean;
  left?: number | null;
}

export interface VideosJob extends Job {
  address: string | null;
  port: number | null;
  code: string | null;
  /** The other machine came in: the copy runs. */
  copying: boolean;
}

export interface AppState {
  preparing: Preparing[];
  videos: VideosJob | null;
  models: Job | null;
  system: 'mac' | 'wsl' | 'linux';
}

export interface Source {
  path: string;
  name: string;
  card: boolean;
  /** Under WSL2, a Windows drive to mount before reading it. */
  drive?: string;
}

export interface Recording {
  start: string | null;
  duration: number;
  chapters: number;
  date: string;
}

export function imageUrl(match: string, kind: 'start' | 'court' | 'background', version = 0): string {
  return `/app/image?match=${encodeURIComponent(match)}&kind=${kind}&v=${version}`;
}

/** The court's landmarks in the order they are clicked (court.LANDMARKS), each at its place on the court in metres:
 * x along the length (net at 0), y across (far sideline at -4.5). */
export const LANDMARKS: [string, number, number][] = [
  ['corner_left_far', -9, -4.5],
  ['attack_left_far', -3, -4.5],
  ['center_far', 0, -4.5],
  ['attack_right_far', 3, -4.5],
  ['corner_right_far', 9, -4.5],
  ['corner_left_near', -9, 4.5],
  ['attack_left_near', -3, 4.5],
  ['center_near', 0, 4.5],
  ['attack_right_near', 3, 4.5],
  ['corner_right_near', 9, 4.5],
  ['post_far', 0, -5.25],
  ['post_near', 0, 5.25],
];

/** The clicks the court's fit needs at least. */
export const MIN_CLICKS = 4;

/** The next landmark to click after `done` of them, clicked or skipped; null when all are. */
export function nextLandmark(done: number): string | null {
  return LANDMARKS[done]?.[0] ?? null;
}

/** The match's teams' names, the first the one on the left at the first rally. */
export function teamNames(item: Pick<Preparing, 'teams' | 'name'>): [string, string] | null {
  const [a, b] = item.teams ?? [];
  return a?.name && b?.name ? [a.name, b.name] : null;
}

/** "m:ss" or "h:mm:ss" read as seconds; null when it is not a time. */
export function parseTime(text: string): number | null {
  const parts = text.trim().split(':');
  if (!text.trim() || parts.length > 3 || parts.some((p) => !/^\d+(\.\d+)?$/.test(p))) {
    return null;
  }
  return parts.reduce((total, p) => total * 60 + Number(p), 0);
}

/** Whether a team's name can be imported: the command line separates the teams with "," and the colour with ":". */
export function validName(name: string): boolean {
  return /^[^,:]+$/.test(name.trim());
}

/** The text key and values saying why an import or a scan was refused (app.py's errors). */
export function importError(error: string | undefined): [string, Record<string, string>] {
  if (error?.startsWith('unreadable:')) {
    return ['app.import.unreadable', { name: error.slice('unreadable:'.length) }];
  }
  if (error?.startsWith('disk:')) {
    return ['app.import.disk', { gb: error.slice('disk:'.length) }];
  }
  const known: Record<string, string> = {
    missing: 'app.import.noFolder',
    empty: 'app.import.noVideo',
    exists: 'app.import.exists',
    times: 'app.import.badTimes',
    running: 'app.import.running',
    mount: 'app.import.mountFailed',
    network: 'app.noAnswer',
  };
  return error && known[error] ? [known[error], {}] : ['app.import.failed', { error: error ?? '' }];
}
