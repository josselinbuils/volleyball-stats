import { describe, expect, it } from 'vitest';
import { fitted, guessTeams } from './brand';

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
});
