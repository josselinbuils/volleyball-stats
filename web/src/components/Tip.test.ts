import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { Slot } from 'radix-ui';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';
import { Tip } from '@/components/Tip';
import { TooltipProvider } from '@/components/ui/tooltip';

describe('Tip', () => {
  const src = fileURLToPath(new URL('..', import.meta.url));
  const uiFolder = join(src, 'components/ui');
  // What renders a DOM element a title would give a native tooltip: an HTML tag or a design system component.
  const ui = readdirSync(uiFolder).flatMap((f) => [...readFileSync(join(uiFolder, f), 'utf8').matchAll(/^export \{([^}]*)\}/gm)].flatMap((m) => m[1].split(',').map((n) => n.trim())));
  const native = (tag: string) => /^[a-z]/.test(tag) || ui.includes(tag);

  it('is the only tooltip: no title makes a native one', () => {
    const found: string[] = [];
    for (const file of readdirSync(src, { recursive: true, encoding: 'utf8' }).filter((f) => f.endsWith('.tsx'))) {
      const source = ts.createSourceFile(file, readFileSync(join(src, file), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      const visit = (node: ts.Node): void => {
        if (ts.isJsxAttribute(node) && node.name.getText() === 'title' && native(node.parent.parent.tagName.getText())) {
          found.push(`${file}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1}`);
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
    expect(ui).toContain('Button');
    expect(found).toEqual([]);
  });

  it('hands the props of a wrapping asChild to its child, with or without a label', () => {
    for (const label of ['Plus', undefined]) {
      const tip = createElement(Tip, { label, children: createElement('button', null, '…') });
      const html = renderToStaticMarkup(createElement(TooltipProvider, null, createElement(Slot.Root, { className: 'wrapped', 'aria-haspopup': 'menu' }, tip)));
      expect(html).toMatch(/<button[^>]*class="wrapped"/);
      expect(html).toContain('aria-haspopup="menu"');
    }
  });
});
