import type { ReactNode } from 'react';

export function Section({ title, caption, children }: { title: string; caption: string; children: ReactNode }) {
  return (
    <section className="grid gap-2">
      <div>
        <h3 className="font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">{caption}</p>
      </div>
      {children}
    </section>
  );
}
