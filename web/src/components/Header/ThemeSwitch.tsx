import { useEffect, useState } from 'react';
import { Moon, Sun, SunMoon } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

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

/** Light, dark or automatic theme, the last following the system's; remembered. */
export function ThemeSwitch() {
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

  const pick = (value: string) => {
    if (!value) {
      return;
    }
    try {
      localStorage.setItem(KEY, value);
    } catch {
      // Storage blocked: the choice lasts until the page closes.
    }
    setMode(value as Mode);
  };

  // The tooltips take over data-state: the picked mode is styled by aria-checked.
  return (
    <ToggleGroup type="single" variant="outline" size="sm" spacing={0} value={mode} onValueChange={pick} aria-label={t('theme')} className="shrink-0 bg-card">
      {Object.entries(MODES).map(([value, Icon]) => (
        <Tooltip key={value}>
          <TooltipTrigger asChild>
            <ToggleGroupItem value={value} aria-label={t(`themes.${value}`)} className="aria-checked:bg-primary aria-checked:text-primary-foreground">
              <Icon aria-hidden />
            </ToggleGroupItem>
          </TooltipTrigger>
          <TooltipContent>{t(`themes.${value}`)}</TooltipContent>
        </Tooltip>
      ))}
    </ToggleGroup>
  );
}
