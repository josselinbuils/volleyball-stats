import { useId, useState } from 'react';
import { Dices, Eye, EyeOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Tip } from '@/components/Tip';
import { INPUT } from '@/lib/app';
import { newPassword } from '@/lib/videoPassword';

/** A password typed hidden, shown on request, `min` characters at least (said once some are typed); with `generate`, a
 * button making a new one, shown. */
export function PasswordField({
  label,
  value,
  onChange,
  min,
  generate = false,
  autoFocus = false,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  min: number;
  generate?: boolean;
  autoFocus?: boolean;
  placeholder?: string;
}) {
  const { t } = useTranslation();
  const id = useId();
  const [shown, setShown] = useState(false);
  const short = value !== '' && value.trim().length < min;

  return (
    <div className="grid gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <div className="flex gap-2">
        <div className="relative min-w-0 flex-1">
          <input
            id={id}
            type={shown ? 'text' : 'password'}
            autoComplete="new-password"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            autoFocus={autoFocus}
            value={value}
            placeholder={placeholder}
            aria-invalid={short || undefined}
            aria-describedby={short ? `${id}-short` : undefined}
            onChange={(e) => onChange(e.target.value)}
            className={`${INPUT} w-full pr-9 ${shown ? 'font-mono' : ''}`}
          />
          <Tip label={t(shown ? 'passwords.hide' : 'passwords.show')}>
            <Button type="button" variant="ghost" size="icon-sm" aria-label={t(shown ? 'passwords.hide' : 'passwords.show')} className="absolute top-1 right-1" onClick={() => setShown((s) => !s)}>
              {shown ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
            </Button>
          </Tip>
        </div>
        {generate && (
          <Tip label={t('passwords.generate')}>
            <Button
              type="button"
              variant="outline"
              size="icon-lg"
              className="bg-card"
              aria-label={t('passwords.generate')}
              onClick={() => {
                onChange(newPassword());
                setShown(true);
              }}
            >
              <Dices aria-hidden />
            </Button>
          </Tip>
        )}
      </div>
      {short && (
        <p id={`${id}-short`} className="m-0 text-xs text-muted-foreground">
          {t('passwords.min', { count: min })}
        </p>
      )}
    </div>
  );
}
