import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

describe('keys', () => {
  const src = fileURLToPath(new URL('..', import.meta.url));

  /** The keys of the elements `child` puts at its place among its siblings: itself, or what a condition shows there. */
  function keysOf(child: ts.Node): string[] {
    if (ts.isJsxExpression(child) || ts.isParenthesizedExpression(child)) {
      return child.expression ? keysOf(child.expression) : [];
    }
    if (ts.isBinaryExpression(child) && [ts.SyntaxKind.AmpersandAmpersandToken, ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken].includes(child.operatorToken.kind)) {
      return keysOf(child.right);
    }
    if (ts.isConditionalExpression(child)) {
      return [...new Set([...keysOf(child.whenTrue), ...keysOf(child.whenFalse)])];
    }
    const opening = ts.isJsxElement(child) ? child.openingElement : ts.isJsxSelfClosingElement(child) ? child : null;
    const key = opening?.attributes.properties.find((a) => ts.isJsxAttribute(a) && a.name.getText() === 'key') as ts.JsxAttribute | undefined;
    return key?.initializer ? [key.initializer.getText()] : [];
  }

  // Two siblings with the same key: React takes one for the other when they change, and leaves a stale copy behind.
  it('differ between the elements written side by side', () => {
    const found: string[] = [];
    for (const file of readdirSync(src, { recursive: true, encoding: 'utf8' }).filter((f) => f.endsWith('.tsx'))) {
      const source = ts.createSourceFile(file, readFileSync(join(src, file), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
      const visit = (node: ts.Node): void => {
        if (ts.isJsxElement(node) || ts.isJsxFragment(node)) {
          const seen = new Set<string>();
          for (const key of node.children.flatMap(keysOf)) {
            if (seen.has(key)) {
              found.push(`${file}:${source.getLineAndCharacterOfPosition(node.getStart()).line + 1} ${key}`);
            }
            seen.add(key);
          }
        }
        ts.forEachChild(node, visit);
      };
      visit(source);
    }
    expect(found).toEqual([]);
  });
});
