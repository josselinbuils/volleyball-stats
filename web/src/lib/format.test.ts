import { describe, expect, it } from 'vitest';
import { formatters, ofName } from '@/lib/format';

describe('ofName', () => {
  it('elides before a vowel', () => {
    expect(ofName('Anthony')).toBe("d'Anthony");
    expect(ofName('Élodie')).toBe("d'Élodie");
    expect(ofName('Olivier')).toBe("d'Olivier");
    expect(ofName('ASPOM 01')).toBe("d'ASPOM 01");
    expect(ofName('Manon')).toBe('de Manon');
  });
});

describe('size', () => {
  it('says bytes in the largest unit, a decimal under 10', () => {
    const { size } = formatters('fr');
    expect(size(158_000_000).replace(/\s/g, ' ')).toBe('158 Mo');
    expect(size(1_311_000_000).replace(/\s/g, ' ')).toBe('1,3 Go');
    expect(formatters('en').size(2_400).replace(/\s/g, ' ')).toBe('2.4 kB');
  });
});
