import { useTranslation } from 'react-i18next';
import { color, DARK_TEXT, type Contact, type Placed } from '@/lib/match';
import { SvgButton } from '@/components/CourtChart/SvgButton';

/** One dot per touch, lettered with its action. */
export function ContactDots({ shown, describe, onPlay }: { shown: Placed[]; describe: (c: Contact) => string; onPlay: (c: Contact) => void }) {
  const { t } = useTranslation();
  return shown.map((c) => (
    <SvgButton key={c.i} label={describe(c)} onActivate={() => onPlay(c)}>
      <circle cx={c.x} cy={c.y} r={0.7} fill="transparent" />
      <circle cx={c.x} cy={c.y} r={0.36} className="dot-mark" fill={color(c.type)} />
      <text x={c.x} y={c.y} className="dot-text" fill={DARK_TEXT.has(c.type) ? '#141413' : '#fff'}>
        {t(`short.${c.type}`)}
      </text>
    </SvgButton>
  ));
}
