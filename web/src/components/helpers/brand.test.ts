import { describe, expect, it } from 'vitest';
import { fitted, guessTeams, suggestedTeams } from './brand';

describe('brand', () => {
  it('shrinks pictures to their height, never enlarging them', () => {
    expect(fitted(1000, 500, 250)).toEqual([500, 250]);
    expect(fitted(100, 50, 250)).toEqual([100, 50]);
  });

  it("guesses the club's teams by its name's first word", () => {
    expect(guessTeams('ASPOM Bègles', ['AVIA 1', 'ASPOM 2', 'aspom 1', 'ASPOMB'])).toEqual(['ASPOM 2', 'aspom 1']);
    expect(guessTeams('Évreux VB', ['Evreux 1'])).toEqual(['Evreux 1']);
    expect(guessTeams('', ['A'])).toEqual([]);
  });

  it("suggests the club's teams first, then the others played", () => {
    const brand = { name: 'ASPOM Bègles', url: null, accent: '', header: '', logo: null, sponsors: [], teams: null };
    expect(suggestedTeams({ brand, played: ['AVIA 1', 'ASPOM 2'] })).toEqual(['ASPOM 2', 'AVIA 1']);
    expect(suggestedTeams({ brand: { ...brand, teams: ['ASPOM 3'] }, played: ['AVIA 1', 'ASPOM 2'] })).toEqual(['ASPOM 3', 'AVIA 1', 'ASPOM 2']);
    expect(suggestedTeams({ brand: null, played: ['B'] })).toEqual(['B']);
  });
});
