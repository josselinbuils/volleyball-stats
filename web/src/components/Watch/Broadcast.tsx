import { useEffect, useMemo, useRef } from 'react';
import { Play, Volume2, VolumeX } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { ofName } from '@/lib/format';
import { cn } from '@/lib/utils';
import { groupName, match, playerLabel, rallies as allRallies, sets, versioned } from '@/lib/match';
import { lineStarting, loadVoice, useRecorded } from '@/lib/voice';
import { usePlayer } from '@/lib/player';
import { useSet } from '@/lib/sets';
import { commentary, lineAt } from '@/components/Watch/helpers/commentary';
import { broadcastClips, replays, type ReplayMoment } from '@/components/Watch/helpers/director';
import type { Score } from '@/components/Watch/helpers/score';

// A recorded line starts within this long of its moment, and a move of the time over this is a jump.
const STARTS_S = 0.5;
const JUMP_S = 1;
const LOADED_AHEAD = 3;

const speaks = () => typeof speechSynthesis !== 'undefined' && typeof SpeechSynthesisUtterance !== 'undefined';

/** Whether the TV view has a voice here: the match's recorded one or the browser's. */
export const canSpeak = () => !!match.voice || speaks();

/** What the TV view shows over the picture: the score, the replay's tag and the commentary. */
export function BroadcastOverlay({ time, rally, replay, score, voice }: { time: number; rally: number | null; replay: ReplayMoment | null; score: Score | null; voice: boolean }) {
  const { t, i18n } = useTranslation();
  const { video } = usePlayer();
  const names = useMemo(() => ({ player: (person: number | null) => (person === null ? null : (match.people[person]?.name ?? null)), team: (g: 1 | 2) => groupName(t, g) }), [t]);
  const said = useMemo(() => commentary(allRallies, names, sets.length), [names]);
  const line = replay ? null : rally === null ? null : lineAt(said.get(rally), time);
  const who = replay && playerLabel(t, replay.contact.person);
  const text = replay ? (who ? t('broadcast.replayOf', { name: who, ofName: ofName(who) }) : t('broadcast.replay')) : line && t(`broadcast.lines.${line.key}`, line.vars);
  const spoken = useRef<string | null>(null);
  // The match's recorded French voice where there is one, else the browser's.
  const live = match.voice && i18n.language === 'fr';
  const recorded = useRecorded();
  const audio = useRef<HTMLAudioElement | null>(null);
  const playing = useRef<string | null>(null);
  const was = useRef(time);
  const ahead = useRef<HTMLAudioElement[]>([]);

  useEffect(() => {
    if (voice && live) {
      loadVoice();
    }
    if (!voice) {
      audio.current?.pause();
      playing.current = null;
    }
  }, [voice, live]);

  useEffect(() => {
    const jumped = Math.abs(time - was.current) > JUMP_S;
    was.current = time;
    if (!voice || !live || !recorded) {
      return;
    }
    audio.current ??= new Audio();
    if (jumped) {
      audio.current.pause();
    }
    if (video?.paused) {
      return;
    }
    const line = lineStarting(recorded.lines, time, STARTS_S);
    const followed = replay && replay.f < 0.1 ? match.people[replay.contact.person ?? -1]?.name : null;
    const file = followed ? recorded.replay[followed] : line?.[1];
    const key = followed ? `replay:${replay?.rally.i}` : line ? `${line[0]}` : null;
    if (file && key && key !== playing.current) {
      playing.current = key;
      audio.current.src = versioned(`voice/${file}`);
      audio.current.play().catch(() => {});
      // The next lines come within a second or two: fetched ahead, they start on time.
      if (line) {
        const at = recorded.lines.indexOf(line);
        ahead.current = recorded.lines.slice(at + 1, at + 1 + LOADED_AHEAD).map(([, next]) => {
          const clip = new Audio(versioned(`voice/${next}`));
          clip.preload = 'auto';
          return clip;
        });
      }
    }
  }, [time, voice, live, recorded, replay, video]);

  // Pausing the match pauses the voice mid-line; playing again carries on.
  useEffect(() => {
    if (!video || !voice || !live) {
      return;
    }
    const pause = () => audio.current?.pause();
    const play = () => {
      if (audio.current?.src && !audio.current.ended && audio.current.currentTime > 0) {
        audio.current.play().catch(() => {});
      }
    };
    video.addEventListener('pause', pause);
    video.addEventListener('play', play);
    return () => {
      video.removeEventListener('pause', pause);
      video.removeEventListener('play', play);
    };
  }, [video, voice, live]);

  useEffect(
    () => () => {
      audio.current?.pause();
    },
    [],
  );

  // A new line is spoken when the voice is on and the match plays: a strong one over the one going on, others only in a silence.
  useEffect(() => {
    if (live || !voice || !speaks() || !text || text === spoken.current || video?.paused) {
      return;
    }
    if (!(line?.strong || replay) && speechSynthesis.speaking) {
      return;
    }
    spoken.current = text;
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = i18n.language === 'fr' ? 'fr-FR' : 'en-GB';
    utterance.rate = 1.1;
    speechSynthesis.speak(utterance);
  }, [live, voice, text, line, replay, video, i18n.language]);

  useEffect(() => {
    if (!voice && speaks()) {
      speechSynthesis.cancel();
      spoken.current = null;
    }
  }, [voice]);
  useEffect(
    () => () => {
      if (speaks()) {
        speechSynthesis.cancel();
      }
    },
    [],
  );

  return (
    <div className="pointer-events-none absolute inset-0 z-[1] overflow-hidden">
      {score && (
        <p className="absolute top-2 left-2 m-0 flex max-w-[calc(100%-1rem)] items-center gap-2 rounded-md bg-black/75 px-2 py-1 text-xs font-semibold text-white tabular-nums sm:text-sm">
          <span className="truncate">{groupName(t, 1)}</span>
          <span>
            {score.score[0]}-{score.score[1]}
          </span>
          <span className="truncate">{groupName(t, 2)}</span>
          <span className="font-normal text-white/70">{t('set', { n: score.set })}</span>
        </p>
      )}
      {replay && <p className="absolute top-2 right-2 m-0 rounded-md bg-primary px-2 py-1 text-xs font-bold tracking-wide text-primary-foreground uppercase">{t('broadcast.replayTag')}</p>}
      <p
        aria-live="off"
        className={cn(
          'absolute inset-x-2 bottom-2 m-0 rounded-md bg-black/75 px-3 py-1.5 text-center text-sm leading-snug font-medium text-white transition-opacity sm:inset-x-[10%] sm:text-base',
          !text && 'opacity-0',
        )}
      >
        {text || ' '}
      </p>
    </div>
  );
}

/** Under the TV view: watching the match shown from the start, and the voice. */
export function BroadcastControls({ voice, onVoice }: { voice: boolean; onVoice: (on: boolean) => void }) {
  const { t } = useTranslation();
  const { play } = usePlayer();
  const { rallies } = useSet();
  const chosen = useMemo(() => replays(allRallies), []);
  const clips = useMemo(() => broadcastClips(rallies, chosen, match.duration), [rallies, chosen]);
  return (
    <div className="mt-3 grid gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={!clips.length} onClick={() => play((tr) => tr('broadcast.watching'), clips)}>
          <Play aria-hidden />
          {t('broadcast.watch')}
        </Button>
        {canSpeak() && (
          <Button size="sm" variant="outline" aria-pressed={voice} onClick={() => onVoice(!voice)}>
            {voice ? <Volume2 aria-hidden /> : <VolumeX aria-hidden />}
            {t(voice ? 'broadcast.voiceOn' : 'broadcast.voiceOff')}
          </Button>
        )}
      </div>
      <p className="m-0 text-[13px] text-muted-foreground">
        {t('broadcast.caption')}
        {match.voice && ` ${t('broadcast.voiceCredit')}`}
      </p>
    </div>
  );
}
