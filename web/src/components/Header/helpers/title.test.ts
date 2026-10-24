import i18next from 'i18next';
import { afterEach, describe, expect, it, vi } from 'vitest';
import en from '@/locales/en.json';
import fr from '@/locales/fr.json';
import { formatters } from '@/lib/format';

describe('match title', () => {
  const i18n = i18next.createInstance();
  void i18n.init({ resources: { fr: { translation: fr }, en: { translation: en } }, lng: 'fr', initAsync: false, interpolation: { escapeValue: false } });
  const named = [
    { name: 'ASPOM Bègles', colour: '#f4f4f4' },
    { name: 'VC Talence', colour: '#1b2a4a' },
  ];
  const unnamed = named.map((team) => ({ ...team, name: null }));

  /** The helpers and team names over a match with these fields. */
  async function load(fields: object) {
    vi.resetModules();
    vi.stubGlobal('window', { MATCH: { name: 'side_setend', video: 'v.mp4', fps: 25, duration: 60, teams: null, rallies: [], contacts: [], zones: [], people: {}, ...fields } });
    const { matchTitle, tabTitle } = await import('@/components/Header/helpers/title');
    const { groupName } = await import('@/lib/match');
    return { matchTitle, tabTitle, groupName };
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('names the teams as the actions table does, the user names or the translated defaults', async () => {
    for (const teams of [named, unnamed]) {
      const { matchTitle, groupName } = await load({ teams, date: '2016-12-21' });
      for (const lang of ['fr', 'en']) {
        const t = i18n.getFixedT(lang);
        expect(matchTitle(t)).toBe(`Match ${groupName(t, 1)} vs ${groupName(t, 2)}`);
      }
    }
    const { matchTitle } = await load({ teams: unnamed });
    expect(matchTitle(i18n.getFixedT('fr'))).toBe('Match Équipe 1 vs Équipe 2');
    expect(matchTitle(i18n.getFixedT('en'))).toBe('Match Team 1 vs Team 2');
  });

  it('shows a typed title as is', async () => {
    expect((await load({ teams: named, title: 'Finale' })).matchTitle(i18n.getFixedT('en'))).toBe('Finale');
  });

  it('adds the date in the page language to the tab title, and keeps the file name without teams', async () => {
    const { tabTitle } = await load({ teams: named, date: '2016-12-21' });
    expect(tabTitle(i18n.getFixedT('fr'), formatters('fr'))).toBe('Match ASPOM Bègles vs VC Talence · 21 décembre 2016');
    expect(tabTitle(i18n.getFixedT('en'), formatters('en'))).toBe('Match ASPOM Bègles vs VC Talence · 21 December 2016');
    expect((await load({ teams: named, title: 'Finale' })).tabTitle(i18n.getFixedT('fr'), formatters('fr'))).toBe('Finale');
    const none = await load({});
    expect(none.matchTitle(i18n.getFixedT('fr'))).toBeNull();
    expect(none.tabTitle(i18n.getFixedT('fr'), formatters('fr'))).toBe('side_setend · Bilan du match');
    expect(none.tabTitle(i18n.getFixedT('en'), formatters('en'))).toBe('side_setend · Match report');
  });
});
