import { describe, expect, it } from 'vitest';
import { ofName } from '@/lib/format';

describe('ofName', () => {
  it('elides before a vowel', () => {
    expect(ofName('Anthony')).toBe("d'Anthony");
    expect(ofName('Élodie')).toBe("d'Élodie");
    expect(ofName('Olivier')).toBe("d'Olivier");
    expect(ofName('ASPOM 01')).toBe("d'ASPOM 01");
    expect(ofName('Manon')).toBe('de Manon');
  });
});
