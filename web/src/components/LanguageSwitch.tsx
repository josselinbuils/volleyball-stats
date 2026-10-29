import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { LANGUAGES, setLanguage, type Language } from '@/i18n';

/** French or English, remembered. */
export function LanguageSwitch() {
  const { t, i18n } = useTranslation();
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      spacing={0}
      value={i18n.language}
      onValueChange={(lang) => {
        if (lang) {
          setLanguage(lang as Language);
        }
      }}
      aria-label={`${t('language')} / ${i18n.language === 'fr' ? 'Language' : 'Langue'}`}
      className="shrink-0 bg-card"
    >
      {Object.entries(LANGUAGES).map(([code, name]) => (
        <ToggleGroupItem key={code} value={code} lang={code} aria-label={name} className="px-3 data-[state=on]:bg-primary data-[state=on]:text-primary-foreground">
          {code.toUpperCase()}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
