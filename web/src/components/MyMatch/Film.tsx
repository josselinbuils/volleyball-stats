import { useEffect, useMemo, useRef, useState } from 'react';
import { Clapperboard, Download, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useFormat } from '@/lib/format';
import { isTouch } from '@/helpers/contacts';
import { playerKey, playersAt } from '@/helpers/players';
import { ball3dLoaded } from '@/lib/ball3d';
import { contacts as allContacts, groupName, match, playerLabel, rallies as allRallies, versioned, type Group } from '@/lib/match';
import { ofName } from '@/components/Watch/helpers/commentary';
import { playersLoaded } from '@/lib/players';
import { voiceLoaded } from '@/lib/voice';
import { lines } from '@/components/Stats/helpers/stats';
import { canDraw3d, loadScene, sceneColors } from '@/components/Watch/Scene3D';
import { bodyOf, posesAt, SPEED_S } from '@/components/Watch/helpers/pose';
import { landingsAt, touchesAt } from '@/components/Watch/helpers/replay';
import { sceneAt } from '@/components/Watch/helpers/sceneAt';
import { scoreAt } from '@/components/Watch/helpers/score';
import { trophies } from '@/components/Trophies/helpers/trophies';
import { FILM_LEAST_MOMENTS, filmMoments, filmShots, liveCamera, momentOf, orbitCamera, shotAt, titleCamera, type Shot } from '@/components/MyMatch/helpers/film';
import { FILM_HEIGHT, FILM_WIDTH, writeOver, type FilmText } from '@/components/MyMatch/helpers/filmPicture';
import { fileName, saveFile } from '@/components/MyMatch/helpers/saveFile';

const FORMATS = ['video/mp4;codecs=avc1.42E01F,mp4a.40.2', 'video/mp4', 'video/webm;codecs=vp9,opus', 'video/webm'];
const VIDEO_BITS = 5_000_000;
const FRAMES = 30;
const TIP_PX = 44;
const STAGE = 'fixed top-0 left-[-10000px]';

const canRecord = () => typeof MediaRecorder !== 'undefined' && 'captureStream' in HTMLCanvasElement.prototype && canDraw3d();

type State = { step: 'idle' | 'preparing' | 'failed' | 'stopped' } | { step: 'recording'; left: number } | { step: 'ready'; url: string; file: File };

/** The commentary's lines a shot plays, with when they start in the film, each after the last has ended; the replay's own about the player. */
function linesFor(shots: Shot[], recorded: Awaited<ReturnType<typeof voiceLoaded>>, name: string | null): { at: number; file: string }[] {
  if (!recorded) {
    return [];
  }
  const out: { at: number; file: string }[] = [];
  let free = 0;
  for (const shot of shots) {
    if (shot.kind === 'live') {
      for (const [t, file, length] of recorded.lines) {
        const at = shot.start + t - shot.from;
        if (at >= Math.max(shot.start, free) && at < shot.start + shot.length) {
          out.push({ at, file });
          free = at + length;
        }
      }
    } else if (shot.kind === 'replay' && name && recorded.replay[name] && shot.start >= free) {
      out.push({ at: shot.start, file: recorded.replay[name] });
      free = shot.start + shot.length;
    }
  }
  return out;
}

/** A vertical film of under 45 seconds of a player's match in the page's 3D reconstruction, made in the browser, with the commentary. */
export function Film({ person, group }: { person: number; group: Group }) {
  const { t, i18n } = useTranslation();
  const f = useFormat();
  const key = playerKey(person, match.people);
  const mine = useMemo(() => allContacts.filter((c) => playerKey(c.person, match.people) === key), [key]);
  const moments = useMemo(() => (key ? filmMoments(allRallies, key, match.people, mine) : []), [key, mine]);
  const [state, setState] = useState<State>({ step: 'idle' });
  const preview = useRef<HTMLCanvasElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const stop = useRef<(() => void) | null>(null);

  useEffect(() => () => stop.current?.(), []);
  useEffect(
    () => () => {
      if (state.step === 'ready') {
        URL.revokeObjectURL(state.url);
      }
    },
    [state],
  );

  if (moments.length < FILM_LEAST_MOMENTS || !key || !canRecord()) {
    return null;
  }

  const make = async () => {
    setState({ step: 'preparing' });
    let cancelled = false;
    let release = () => {};
    stop.current = () => {
      cancelled = true;
      release();
    };
    try {
      const { shots, length } = filmShots(moments, allRallies);
      const shown = shots.filter((s) => s.kind === 'live' || s.kind === 'replay').flatMap((s) => [s.from, s.from + s.length * s.speed]);
      const [places, players] = await Promise.all([ball3dLoaded(), playersLoaded(shown), loadScene()]).then(([a, b]) => [a, b] as const);
      const name = match.people[person]?.name ?? null;
      const recorded = match.voice && i18n.language === 'fr' ? await voiceLoaded() : null;
      const audio = new AudioContext();
      const sound = audio.createMediaStreamDestination();
      const said = await Promise.all(
        linesFor(shots, recorded, name).map(async ({ at, file }) => {
          try {
            const reply = await fetch(versioned(`voice/${file}`));
            return { at, buffer: await audio.decodeAudioData(await reply.arrayBuffer()) };
          } catch {
            return null;
          }
        }),
      );
      const canvas = preview.current;
      const box = stage.current;
      const painter = canvas?.getContext('2d');
      if (cancelled || !canvas || !box || !painter || !window.VolleyScene) {
        await audio.close();
        return;
      }
      const scene = window.VolleyScene.mount(box, match.brand?.sponsors ?? [], { pixelRatio: 1, manual: true, tipPx: TIP_PX });
      const colors = sceneColors();
      // The stage takes its size on the next frame.
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const line = lines(allContacts, match.people, group).find((l) => l.id === person);
      const won = trophies(
        ([1, 2] as const).flatMap((g) => lines(allContacts, match.people, g)),
        allContacts,
        allRallies,
        match.people,
      )
        .filter((x) => 'people' in x && x.people.some((p) => playerKey(p, match.people) === key))
        .map((x) => t(`trophies.names.${x.kind}`));
      const speeds = mine.flatMap((c) => (c.speed === undefined ? [] : [c.speed]));
      const stats = line?.stats;
      const label = playerLabel(t, person) ?? '';
      const text: FilmText = {
        name: label,
        // "de" or "d'", alone: the name is written below it.
        titleAbove: t('myMatch.film.titleAbove', { of: ofName(label).replace(label, '').trim() }),
        titleBelow: [groupName(t, group), match.date && f.date(match.date)].filter(Boolean).join(' · '),
        endLines: [
          stats && t('myMatch.summaryPoints', { count: stats.points.length }),
          stats && t('myMatch.summaryTouches', { count: stats.touches.length }),
          speeds.length ? t('myMatch.fastestServe', { speed: Math.max(...speeds) }) : null,
          ...won.slice(0, 3),
        ].filter((x): x is string => !!x),
        replayTag: t('broadcast.replayTag'),
        primary: colors.primary,
        scoreOf: (time) => {
          const shot = shotAt(shots, time);
          const score = scoreAt(allRallies, shot.kind === 'replay' ? shot.rally.start : momentOf(shot, time), match.scores);
          return score && { left: groupName(t, 1), score: `${score.score[0]}-${score.score[1]}`, right: groupName(t, 2), set: t('set', { n: score.set }) };
        },
        action: (shot) => {
          const c = shot.contact;
          return c.speed !== undefined ? t('myMatch.film.serveSpeed', { speed: c.speed }) : t(`actions.${c.type}.${c.result}`);
        },
      };
      const frame = (time: number) => {
        const shot = shotAt(shots, time);
        const moment = momentOf(shot, Math.min(time, shot.start + shot.length));
        const rally = shot.rally;
        const dots = typeof players === 'object' ? playersAt(players, match.fps, moment) : [];
        const poses =
          typeof players === 'object' ? posesAt(rally, moment, dots, playersAt(players, match.fps, moment - SPEED_S), playersAt(players, match.fps, moment + SPEED_S), places, match.people) : null;
        const hero = dots.find((d) => playerKey(d.person, match.people) === key);
        const first = rally.contacts.find(isTouch);
        const score = scoreAt(allRallies, moment, match.scores);
        const camera =
          shot.kind === 'live'
            ? liveCamera(shot, moment, places)
            : shot.kind === 'replay'
              ? orbitCamera(shot, moment, { x: hero?.x ?? shot.contact.x ?? 0, y: hero?.y ?? shot.contact.y ?? 0 }, places)
              : titleCamera(time);
        const titled = shot.kind === 'intro' || shot.kind === 'outro';
        scene.update({
          ...sceneAt({
            dots,
            poses,
            rally,
            moment,
            touches: titled ? [] : touchesAt(rally.contacts, moment),
            landings: titled ? [] : landingsAt(rally.contacts, moment),
            server: first && bodyOf(first, places?.get(first.i) ?? null, dots, match.people),
            places,
            board: score && { teams: [groupName(t, 1), groupName(t, 2)], score: score.score, set: t('set', { n: score.set }) },
            camera,
            hidden: null,
            tipOf: (p) => (shot.kind === 'live' && p === hero?.person ? text.name : undefined),
          }),
          colors,
        });
        scene.render();
        painter.fillStyle = '#000';
        painter.fillRect(0, 0, FILM_WIDTH, FILM_HEIGHT);
        painter.drawImage(scene.canvas, 0, 0, FILM_WIDTH, FILM_HEIGHT);
        writeOver(painter, shot, time, text);
      };
      frame(0);

      const video = canvas.captureStream(FRAMES);
      const recorder = new MediaRecorder(new MediaStream([...video.getVideoTracks(), ...sound.stream.getAudioTracks()]), {
        mimeType: FORMATS.find((x) => MediaRecorder.isTypeSupported(x)),
        videoBitsPerSecond: VIDEO_BITS,
      });
      const chunks: Blob[] = [];
      recorder.ondataavailable = (e) => chunks.push(e.data);
      let raf = 0;
      let ended = false;
      const close = () => {
        if (ended) {
          return;
        }
        ended = true;
        cancelAnimationFrame(raf);
        document.removeEventListener('visibilitychange', hide);
        video.getTracks().forEach((track) => track.stop());
        scene.dispose();
        void audio.close();
        stop.current = null;
      };
      const hide = () => {
        if (document.hidden) {
          recorder.onstop = null;
          recorder.stop();
          close();
          setState({ step: 'stopped' });
        }
      };
      release = () => {
        recorder.onstop = null;
        if (recorder.state !== 'inactive') {
          recorder.stop();
        }
        close();
      };
      recorder.onstop = () => {
        close();
        const type = recorder.mimeType.split(';')[0];
        const blob = new Blob(chunks, { type });
        const extension = type === 'video/mp4' ? 'mp4' : 'webm';
        setState({ step: 'ready', url: URL.createObjectURL(blob), file: new File([blob], `film-${fileName(text.name)}.${extension}`, { type }) });
      };
      document.addEventListener('visibilitychange', hide);
      await audio.resume();
      recorder.start(1000);
      const began = performance.now();
      const startedAudio = audio.currentTime;
      for (const clip of said) {
        if (clip) {
          const source = audio.createBufferSource();
          source.buffer = clip.buffer;
          source.connect(sound);
          source.connect(audio.destination);
          source.start(startedAudio + clip.at);
        }
      }
      let shownLeft = -1;
      const tick = () => {
        const time = (performance.now() - began) / 1000;
        if (time >= length) {
          recorder.stop();
          return;
        }
        frame(time);
        const left = Math.ceil(length - time);
        if (left !== shownLeft) {
          shownLeft = left;
          setState({ step: 'recording', left });
        }
        raf = requestAnimationFrame(tick);
      };
      setState({ step: 'recording', left: Math.ceil(length) });
      tick();
    } catch {
      stop.current?.();
      setState({ step: 'failed' });
    }
  };

  const busy = state.step === 'preparing' || state.step === 'recording';
  return (
    <div className="grid justify-items-start gap-2">
      {state.step !== 'ready' && !busy && (
        <Button variant="outline" onClick={() => void make()}>
          <Clapperboard aria-hidden />
          {t('myMatch.film.create')}
        </Button>
      )}
      {(state.step === 'failed' || state.step === 'stopped') && <p className="text-sm text-muted-foreground">{t(`myMatch.film.${state.step}`)}</p>}
      {busy && <p className="text-sm text-muted-foreground">{state.step === 'recording' ? t('myMatch.film.recording', { left: state.left }) : t('myMatch.film.preparing')}</p>}
      <div ref={stage} aria-hidden className={STAGE} style={{ width: FILM_WIDTH, height: FILM_HEIGHT }} />
      <canvas ref={preview} width={FILM_WIDTH} height={FILM_HEIGHT} className={state.step === 'recording' ? 'w-56 rounded-lg bg-black' : 'hidden'} />
      {state.step === 'ready' && (
        <>
          <video src={state.url} controls playsInline className="w-56 rounded-lg bg-black" />
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => saveFile(state.file)}>
              <Download aria-hidden />
              {t('myMatch.film.save')}
            </Button>
            <Button variant="outline" onClick={() => void make()}>
              <RotateCcw aria-hidden />
              {t('myMatch.film.again')}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
