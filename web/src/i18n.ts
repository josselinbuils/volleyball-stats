import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from '@/locales/en.json';
import fr from '@/locales/fr.json';

export const LANGUAGES = { fr: 'Français', en: 'English' } as const;
export type Language = keyof typeof LANGUAGES;

const KEY = 'volleyball-stats-lang';

function saved(): Language {
  try {
    const lang = localStorage.getItem(KEY);
    if (lang && lang in LANGUAGES) {
      return lang as Language;
    }
  } catch {
    // Storage blocked: French.
  }
  return 'fr';
}

/** Switches the page's language and remembers the choice. */
export function setLanguage(lang: Language) {
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    // Storage blocked: the choice lasts until the page closes.
  }
  void i18n.changeLanguage(lang);
}

// French whatever the browser's language, unless the visitor picked another one.
void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr }, en: { translation: en } },
  lng: saved(),
  fallbackLng: 'en',
  initAsync: false,
  interpolation: { escapeValue: false },
});
document.documentElement.lang = i18n.language;
i18n.on('languageChanged', (lang) => {
  document.documentElement.lang = lang;
});
