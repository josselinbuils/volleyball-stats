import { useEffect, useState } from 'react';
import { ChevronDown, Moon, Sun, SunMoon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Tip } from '@/components/Tip';
import { LANGUAGES, setLanguage, type Language } from '@/i18n';
import { cn } from '@/lib/utils';

const MODES = { light: Sun, dark: Moon, auto: SunMoon } as const;
type Mode = keyof typeof MODES;

// index.html reads it too, to set the theme before the first paint.
const KEY = 'volleyball-stats-theme';

function saved(): Mode {
  try {
    const mode = localStorage.getItem(KEY);
    if (mode && mode in MODES) {
      return mode as Mode;
    }
  } catch {
    // Storage blocked: automatic.
  }
  return 'auto';
}

const look = (onBar: boolean) =>
  cn(
    'inline-flex h-9 min-w-9 shrink-0 items-center justify-center gap-1 rounded-md px-1.5 text-sm font-semibold outline-none focus-visible:ring-3 [&_svg]:shrink-0',
    onBar ? 'text-white hover:bg-white/15 focus-visible:ring-white/70 aria-expanded:bg-white/15' : 'hover:bg-muted focus-visible:ring-ring/50 aria-expanded:bg-muted',
  );

/** The theme and the language, each a menu, remembered; `onBar` on the club's dark band. */
export function Settings({ onBar = false }: { onBar?: boolean }) {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <ThemeMenu onBar={onBar} />
      <LanguageMenu onBar={onBar} />
    </div>
  );
}

/** Light, dark or automatic theme, the last following the system's. */
function ThemeMenu({ onBar }: { onBar: boolean }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState(saved);

  useEffect(() => {
    const system = matchMedia('(prefers-color-scheme: dark)');
    const apply = () => document.documentElement.classList.toggle('dark', mode === 'dark' || (mode === 'auto' && system.matches));
    apply();
    if (mode !== 'auto') {
      return;
    }
    system.addEventListener('change', apply);
    return () => system.removeEventListener('change', apply);
  }, [mode]);

  const pick = (value: Mode) => {
    try {
      localStorage.setItem(KEY, value);
    } catch {
      // Storage blocked: the choice lasts until the page closes.
    }
    setMode(value);
  };
  const Icon = MODES[mode];
  return (
    <DropdownMenu>
      <Tip label={t('theme')}>
        <DropdownMenuTrigger aria-label={`${t('theme')} : ${t(`themes.${mode}`)}`} className={look(onBar)}>
          <Icon aria-hidden className="size-5" />
        </DropdownMenuTrigger>
      </Tip>
      <DropdownMenuContent>
        {(Object.entries(MODES) as [Mode, (typeof MODES)[Mode]][]).map(([value, ItemIcon]) => (
          <DropdownMenuCheckboxItem key={value} checked={mode === value} onCheckedChange={() => pick(value)}>
            <ItemIcon aria-hidden />
            {t(`themes.${value}`)}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** French or English. */
function LanguageMenu({ onBar }: { onBar: boolean }) {
  const { t, i18n } = useTranslation();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger aria-label={`${t('language')} / ${i18n.language === 'fr' ? 'Language' : 'Langue'} : ${LANGUAGES[i18n.language as Language]}`} className={look(onBar)}>
        {i18n.language.toUpperCase()}
        <ChevronDown aria-hidden className="size-3.5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="min-w-36">
        {(Object.entries(LANGUAGES) as [Language, string][]).map(([code, name]) => (
          <DropdownMenuCheckboxItem key={code} lang={code} checked={i18n.language === code} onCheckedChange={() => setLanguage(code)}>
            {name}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
