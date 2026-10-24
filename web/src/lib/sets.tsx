import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { contacts, rallies, type Contact, type Rally } from '@/lib/match';

/** The set picked for the whole page, null for every set, with its rallies and touches. */
interface Picked {
  set: number | null;
  pick: (set: number | null) => void;
  rallies: Rally[];
  contacts: Contact[];
}

const SetContext = createContext<Picked | null>(null);

export function SetProvider({ children }: { children: ReactNode }) {
  const [set, pick] = useState<number | null>(null);
  const value = useMemo(
    () => ({
      set,
      pick,
      rallies: set === null ? rallies : rallies.filter((r) => r.set === set),
      contacts: set === null ? contacts : contacts.filter((c) => c.set === set),
    }),
    [set],
  );
  return <SetContext.Provider value={value}>{children}</SetContext.Provider>;
}

export function useSet(): Picked {
  const picked = useContext(SetContext);
  if (!picked) {
    throw new Error('useSet needs a SetProvider');
  }
  return picked;
}
