import { useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ofName } from '@/lib/format';
import { groupName, match, playerLabel, rallies as allRallies, sets, versioned } from '@/lib/match';
import { lineStarting, loadVoice, recordedIn, useCommentary, useRecorded } from '@/lib/voice';
import { setUnder, usePlayer } from '@/lib/player';
import { commentary, lineAt, type Line } from '@/components/Watch/helpers/commentary';
import type { ReplayMoment } from '@/components/Watch/helpers/director';

// A recorded line starts within this long of its moment, and a move of the time over this is a jump.
const STARTS_S = 0.5;
const JUMP_S = 1;
const LOADED_AHEAD = 3;
// While a line is spoken the match's own sound drops to this share of its volume (about -10 dB), over this long, and comes back over
// this long once the voice has been quiet that long (two lines close together keep it down).
const DUCKED = 0.3;
const DUCK_MS = 150;
const BACK_MS = 600;
const QUIET_MS = 800;
// A recorded line's words stay this long after it is said, at least this long in all.
const HELD_S = 1.5;
const SHOWN_S = 3;

export const speaks = () => typeof speechSynthesis !== 'undefined' && typeof SpeechSynthesisUtterance !== 'undefined';

/** What the commentary says at `time` in `rally` (null between rallies), or of the TV view's `replay`: the recorded
 * voice's own words where it speaks (remarks between rallies included), else the page's lines. */
export function useSaid(time: number, rally: number | null, replay: ReplayMoment | null): { text: string | null; line: Line | null } {
  const { t, i18n } = useTranslation();
  const recorded = useRecorded();
  const names = useMemo(() => ({ player: (person: number | null) => (person === null ? null : (match.people[person]?.name ?? null)), team: (g: 1 | 2) => groupName(t, g) }), [t]);
  const said = useMemo(() => commentary(allRallies, names, sets.length), [names]);
  const who = replay && playerLabel(t, replay.contact.person);
  if (replay) {
    return { text: who ? t('broadcast.replayOf', { name: who, ofName: ofName(who) }) : t('broadcast.replay'), line: null };
  }
  // A build before the words were kept has none: the page's lines then.
  if (recorded && recordedIn(i18n.language) && recorded.lines[0]?.[3] !== undefined) {
    const row = recorded.lines.findLast(([at]) => at <= time);
    return { text: row && time - row[0] < Math.max(row[2] + HELD_S, SHOWN_S) ? (row[3] ?? null) : null, line: null };
  }
  const line = rally === null ? null : lineAt(said.get(rally), time);
  return { text: (line && t(`broadcast.lines.${line.key}`, line.vars)) || null, line };
}

/** The commentary heard with the match while it plays, when it is on: the match's recorded French voice where there is
 * one, else the browser's; the match's own sound lowered under it. `replay` is the TV view's, when shown. */
export function Commentary({ time, rally, replay }: { time: number; rally: number | null; replay: ReplayMoment | null }) {
  const { i18n } = useTranslation();
  const { video } = usePlayer();
  const on = useCommentary();
  const { text, line } = useSaid(time, rally, replay);
  const live = recordedIn(i18n.language);
  const recorded = useRecorded();
  const audio = useRef<HTMLAudioElement | null>(null);
  const playing = useRef<string | null>(null);
  const spoken = useRef<string | null>(null);
  const was = useRef(time);
  const ahead = useRef<HTMLAudioElement[]>([]);
  const sound = video instanceof HTMLVideoElement ? video : null;

  // The match's sound under the voice: lowered at once, back after a silence.
  const duck = useRef<(down: boolean) => void>(() => {});
  useEffect(() => {
    let share = 1;
    let down = false;
    let frame = 0;
    let timer = 0;
    const fade = (to: number, ms: number) => {
      cancelAnimationFrame(frame);
      const from = share;
      const start = performance.now();
      const step = (now: number) => {
        const k = Math.min(1, (now - start) / ms);
        share = from + (to - from) * k;
        setUnder(share);
        if (k < 1) {
          frame = requestAnimationFrame(step);
        }
      };
      frame = requestAnimationFrame(step);
    };
    duck.current = (next) => {
      clearTimeout(timer);
      if (next && !down) {
        down = true;
        fade(DUCKED, DUCK_MS);
      } else if (!next && down) {
        timer = window.setTimeout(() => {
          down = false;
          fade(1, BACK_MS);
        }, QUIET_MS);
      }
    };
    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(frame);
      setUnder(1);
      duck.current = () => {};
    };
  }, []);

  useEffect(() => {
    if (on && live) {
      loadVoice();
    }
    if (!on) {
      audio.current?.pause();
      playing.current = null;
      duck.current(false);
    }
  }, [on, live]);

  // The recorded voice: each line from its moment, cut by a jump in the match.
  useEffect(() => {
    const jumped = Math.abs(time - was.current) > JUMP_S;
    was.current = time;
    if (!on || !live || !recorded) {
      return;
    }
    if (!audio.current) {
      const clip = new Audio();
      clip.addEventListener('playing', () => duck.current(true));
      clip.addEventListener('pause', () => duck.current(false));
      clip.addEventListener('ended', () => duck.current(false));
      audio.current = clip;
    }
    if (jumped) {
      audio.current.pause();
    }
    if (video?.paused) {
      return;
    }
    const at = lineStarting(recorded.lines, time, STARTS_S);
    const followed = replay && replay.f < 0.1 ? match.people[replay.contact.person ?? -1]?.name : null;
    const file = followed ? recorded.replay[followed] : at?.[1];
    const key = followed ? `replay:${replay?.rally.i}` : at ? `${at[0]}` : null;
    if (file && key && key !== playing.current) {
      playing.current = key;
      audio.current.muted = sound?.muted ?? false;
      audio.current.src = versioned(`voice/${file}`);
      audio.current.play().catch(() => {});
      // The next lines come within a second or two: fetched ahead, they start on time.
      if (at) {
        const next = recorded.lines.indexOf(at);
        ahead.current = recorded.lines.slice(next + 1, next + 1 + LOADED_AHEAD).map(([, name]) => {
          const clip = new Audio(versioned(`voice/${name}`));
          clip.preload = 'auto';
          return clip;
        });
      }
    }
  }, [time, on, live, recorded, replay, video, sound]);

  // Pausing the match pauses the voice mid-line; playing again carries on. Muting the match mutes it too.
  useEffect(() => {
    if (!video || !on) {
      return;
    }
    const pause = () => {
      audio.current?.pause();
      if (speaks()) {
        speechSynthesis.cancel();
      }
    };
    const play = () => {
      if (audio.current?.src && !audio.current.ended && audio.current.currentTime > 0) {
        audio.current.play().catch(() => {});
      }
    };
    const mute = () => {
      if (audio.current && sound) {
        audio.current.muted = sound.muted;
      }
      if (sound?.muted && speaks()) {
        speechSynthesis.cancel();
      }
    };
    video.addEventListener('pause', pause);
    video.addEventListener('play', play);
    sound?.addEventListener('volumechange', mute);
    return () => {
      video.removeEventListener('pause', pause);
      video.removeEventListener('play', play);
      sound?.removeEventListener('volumechange', mute);
    };
  }, [video, sound, on]);

  // The browser's voice: a strong line over the one going on, others only in a silence.
  useEffect(() => {
    if (live || !on || !speaks() || !text || text === spoken.current || video?.paused || sound?.muted) {
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
    utterance.onstart = () => duck.current(true);
    utterance.onend = () => duck.current(false);
    utterance.onerror = () => duck.current(false);
    speechSynthesis.speak(utterance);
  }, [live, on, text, line, replay, video, sound, i18n.language]);

  useEffect(() => {
    if (!on && speaks()) {
      speechSynthesis.cancel();
      spoken.current = null;
    }
  }, [on]);
  useEffect(
    () => () => {
      audio.current?.pause();
      if (speaks()) {
        speechSynthesis.cancel();
      }
    },
    [],
  );
  return null;
}
