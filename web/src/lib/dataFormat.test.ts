import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { expect, test } from 'vitest';

/* What a page reads from its data files, which online pages of the same data format (web.FORMAT) share one code for: data
 * built before a change must still read with the code after it. The shape kept in dataFormat.json, each file's type spelled
 * out, must fit today's types: a new field optional, read with a fallback. A field gone or changed raises FORMAT in web.py,
 * the pages built before keeping the code they were built with. Either way `UPDATE_FORMAT=1 npx vitest run dataFormat` keeps
 * the new shape. */

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, '..', '..');
const SNAPSHOT = join(here, 'dataFormat.json');
// The files a page loads its data from, by the global each sets; a function's arguments for the positions' files.
const FILES = ['lib/match.ts', 'lib/players.ts', 'lib/video.ts', 'lib/ball3d.ts', 'lib/voice.ts'].map((f) => join(web, 'src', f));
const GLOBALS = ['MATCH', 'MATCH_POSITIONS', 'MATCH_VIDEO', 'MATCH_BALL3D', 'MATCH_VOICE'];
const CHECK = join(web, 'src', '__dataFormatCheck.ts');

const pythonFormat = () => Number(/^FORMAT = (\d+)$/m.exec(readFileSync(join(web, '..', 'src', 'volleyball_stats', 'web.py'), 'utf8'))![1]);

function program(extra?: string) {
  const config = ts.getParsedCommandLineOfConfigFile(join(web, 'tsconfig.json'), {}, { ...ts.sys, onUnRecoverableConfigFileDiagnostic: () => {} })!;
  const host = ts.createCompilerHost(config.options);
  const read = host.readFile;
  host.readFile = (file) => (extra !== undefined && file === CHECK ? extra : read(file));
  const exists = host.fileExists;
  host.fileExists = (file) => (extra !== undefined && file === CHECK) || exists(file);
  return ts.createProgram([...FILES, ...(extra !== undefined ? [CHECK] : [])], config.options, host);
}

/** `type` spelled out with no name, as the data must be. */
function spell(checker: ts.TypeChecker, type: ts.Type, depth = 0): string {
  if (depth > 12) {
    return 'unknown';
  }
  const next = (t: ts.Type) => spell(checker, t, depth + 1);
  if (type.isUnion()) {
    return [...new Set(type.types.map(next))].sort().join(' | ');
  }
  // A leaf: its name, a literal's value.
  const LEAF = [
    'String',
    'Number',
    'Boolean',
    'BigInt',
    'ESSymbol',
    'StringLiteral',
    'NumberLiteral',
    'BooleanLiteral',
    'BigIntLiteral',
    'EnumLiteral',
    'Null',
    'Undefined',
    'Void',
    'Any',
    'Unknown',
    'Never',
  ] as const;
  if (LEAF.some((flag) => type.flags & ts.TypeFlags[flag])) {
    return checker.typeToString(type);
  }
  if (checker.isTupleType(type)) {
    return `[${checker
      .getTypeArguments(type as ts.TypeReference)
      .map(next)
      .join(', ')}]`;
  }
  if (checker.isArrayType(type)) {
    return `(${next(checker.getTypeArguments(type as ts.TypeReference)[0])})[]`;
  }
  const call = type.getCallSignatures()[0];
  if (call) {
    const params = call.getParameters().map((p) => `${p.name}: ${next(checker.getTypeOfSymbol(p))}`);
    return `((${params.join(', ')}) => ${next(call.getReturnType())})`;
  }
  const fields = checker.getPropertiesOfType(type).map((p) => {
    const optional = p.flags & ts.SymbolFlags.Optional ? '?' : '';
    // Optional, its `undefined` once: the type a field may be absent with, its null kept.
    const field = checker.getTypeOfSymbol(p);
    const kept = optional && field.isUnion() ? field.types.filter((t) => !(t.flags & ts.TypeFlags.Undefined)) : [field];
    return `${JSON.stringify(p.name)}${optional}: ${[...new Set(kept.map(next))].sort().join(' | ')}${optional ? ' | undefined' : ''}`;
  });
  const indexes = checker.getIndexInfosOfType(type).map((info) => `[k: ${checker.typeToString(info.keyType)}]: ${next(info.type)}`);
  return `{ ${[...indexes, ...fields].join('; ')} }`;
}

/** Each global's data as today's code types it: what a data file sets, or the arguments it calls the global with. */
function shapes(): Record<string, string> {
  const p = program();
  const checker = p.getTypeChecker();
  const found: Record<string, string> = {};
  for (const file of FILES) {
    const source = p.getSourceFile(file)!;
    source.forEachChild(function visit(node) {
      if (ts.isInterfaceDeclaration(node) && node.name.text === 'Window') {
        for (const member of node.members) {
          const name = member.name && ts.isIdentifier(member.name) ? member.name.text : '';
          if (GLOBALS.includes(name)) {
            const type = checker.getNonNullableType(checker.getTypeAtLocation(member));
            const call = type.getCallSignatures()[0];
            found[name] = call
              ? `[${call
                  .getParameters()
                  .map((s) => spell(checker, checker.getTypeOfSymbol(s)))
                  .join(', ')}]`
              : spell(checker, type);
          }
        }
      }
      node.forEachChild(visit);
    });
  }
  return found;
}

test('data built before still reads with this code, else its format is raised', { timeout: 60_000 }, () => {
  const now = shapes();
  expect(Object.keys(now).sort()).toEqual([...GLOBALS].sort());
  const format = pythonFormat();
  if (process.env.UPDATE_FORMAT) {
    writeFileSync(SNAPSHOT, `${JSON.stringify({ format, shapes: now }, null, 1)}\n`);
    return;
  }
  const kept = JSON.parse(readFileSync(SNAPSHOT, 'utf8')) as { format: number; shapes: Record<string, string> };
  if (kept.format !== format) {
    throw new Error(`web.FORMAT is ${format}, dataFormat.json's ${kept.format}: UPDATE_FORMAT=1 npx vitest run dataFormat`);
  }
  // Older data, each global's as kept, given where today's code takes it.
  const check = GLOBALS.map((name) => {
    const target = name === 'MATCH_POSITIONS' ? `Parameters<NonNullable<Window['${name}']>>` : `NonNullable<Window['${name}']>`;
    return `declare const old_${name}: ${kept.shapes[name]};\nexport const new_${name}: ${target} = old_${name};\n`;
  });
  const p = program(check.join(''));
  const errors = ts.getPreEmitDiagnostics(p, p.getSourceFile(CHECK)).map((d) => ts.flattenDiagnosticMessageText(d.messageText, '\n'));
  if (errors.length) {
    throw new Error(`Data built before no longer fits the page's types: raise FORMAT in web.py, then UPDATE_FORMAT=1 npx vitest run dataFormat.\n${errors.join('\n')}`);
  }
  for (const name of GLOBALS) {
    expect(now[name], `${name}'s shape changed and still reads older data: UPDATE_FORMAT=1 npx vitest run dataFormat keeps it`).toBe(kept.shapes[name]);
  }
});
