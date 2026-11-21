import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { normalizePath, type Plugin } from 'vite';

/** The online pages' builds (the match page, the list) made from their own code only, so that a change of the review or of
 * the app's screens never changes them, nor shows them late: Tailwind takes the classes of their modules alone, the
 * locales keep the texts their code names, and a build reaching one of the app's own modules (LOCAL) fails. The app's
 * scripts (review-app.js, app.js) carry every style and text themselves (`lib/sheet.ts`). */

// As Vite names the modules, on Windows too.
const SRC = normalizePath(resolve(import.meta.dirname, 'src'));
const CSS = `${SRC}/index.css`;
const LOCALES = `${SRC}/locales`;
const EXTENSIONS = ['', '.ts', '.tsx', '/index.ts', '/index.tsx'];
// The app's own modules, by their path under src/: only review-app.js and app.js load them.
const LOCAL = [
  /^components\/(Review|Setup|Progress)\//,
  /^components\/(AppMatches|SiteTab|Tasks|Behind|NewReports|Update|ExportSite|VideoPassword)\.tsx$/,
  /^(reviewApp|appPanel)\.tsx$/,
  /^lib\/(review|tasks|openMatch|remoteMatches|sheet)\.ts$/,
];
// An import or a re-export, and its source: type-only ones load nothing.
const IMPORT = /^\s*(?:import|export)\s+(type\s+)?(?:([^'";]*?)\s+from\s+)?['"]([^'"]+)['"]/gm;

function resolveImport(from: string, spec: string): string | null {
  const bare = spec.split('?')[0];
  const base = bare.startsWith('@/') ? resolve(SRC, bare.slice(2)) : bare.startsWith('.') ? resolve(dirname(from), bare) : null;
  const found = base && EXTENSIONS.map((ext) => base + ext).find((path) => existsSync(path) && statSync(path).isFile());
  return found ? normalizePath(found) : null;
}

/** The files of src/ that `entry` loads, itself included, through its imports but the type-only ones. */
export function sourceGraph(entry: string): Set<string> {
  const seen = new Set<string>();
  const todo = [normalizePath(resolve(entry))];
  while (todo.length) {
    const file = todo.pop()!;
    if (seen.has(file)) {
      continue;
    }
    seen.add(file);
    if (!/\.tsx?$/.test(file)) {
      continue;
    }
    for (const [, type, names, spec] of readFileSync(file, 'utf8').matchAll(IMPORT)) {
      const onlyTypes =
        type ||
        (names &&
          /^\{[^}]*\}$/.test(names.trim()) &&
          names
            .slice(1, -1)
            .split(',')
            .every((n) => !n.trim() || /^type\s/.test(n.trim())));
      const path = onlyTypes ? null : resolveImport(file, spec);
      if (path) {
        todo.push(path);
      }
    }
  }
  return seen;
}

/** The text keys the code `sources` may name: its literals ("a.b"), and the starts of the keys it builds ('a.' + x, `a.${x}`). */
export function namedKeys(sources: string[]): { exact: Set<string>; starts: Set<string> } {
  const exact = new Set<string>();
  const starts = new Set<string>();
  for (const source of sources) {
    for (const [, , text, plus] of source.matchAll(/(['"`])([A-Za-z][\w.]*)\1(\s*\+)?/g)) {
      (plus || text.endsWith('.') ? starts : exact).add(text);
    }
    for (const [, text] of source.matchAll(/`([A-Za-z][\w.]*)\$\{/g)) {
      starts.add(text);
    }
  }
  return { exact, starts };
}

type Texts = { [key: string]: string | Texts };

/** `texts` with only the keys `named` names (a plural's forms by their key without the form); `touch` keeps the touch
 * screens' versions of the texts kept. */
export function keptTexts(texts: Texts, named: { exact: Set<string>; starts: Set<string> }): Texts {
  const names = (key: string) => {
    const bare = key.replace(/_(zero|one|two|few|many|other)$/, '');
    return named.exact.has(key) || named.exact.has(bare) || [...named.starts].some((start) => key.startsWith(start));
  };
  // `at`: the key of `tree`'s texts before theirs.
  const keep = (tree: Texts, at: string): Texts => {
    const out: Texts = {};
    for (const [key, value] of Object.entries(tree)) {
      if (typeof value === 'string') {
        if (names(at + key)) {
          out[key] = value;
        }
      } else {
        const inner = keep(value, `${at}${key}.`);
        if (Object.keys(inner).length) {
          out[key] = inner;
        }
      }
    }
    return out;
  };
  const { touch, ...rest } = texts;
  return { ...keep(rest, ''), touch: typeof touch === 'object' ? keep(touch, '') : {} };
}

/** The plugin for the online build of `page` (index.html, matches.html) and its script `entry` (main.tsx, matches.tsx, in
 * src/); before Tailwind's. */
export function online(page: string, entry: string): Plugin {
  const graph = sourceGraph(`${SRC}/${entry}`);
  const code = [...graph].filter((path) => /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path));
  const named = namedKeys(code.map((path) => readFileSync(path, 'utf8')));
  return {
    name: 'online',
    apply: 'build',
    enforce: 'pre',
    transform(source, id) {
      if (id === CSS) {
        const sources = [`../${page}`, ...code.map((path) => `./${relative(SRC, path).replaceAll('\\', '/')}`)].map((path) => `@source "${path}";`).join('\n');
        return source.replace("@import 'tailwindcss';", "@import 'tailwindcss' source(none);") + `\n${sources}\n`;
      }
      if (dirname(id) === LOCALES && id.endsWith('.json')) {
        return JSON.stringify(keptTexts(JSON.parse(source) as Texts, named));
      }
      return null;
    },
    generateBundle(_, bundle) {
      for (const chunk of Object.values(bundle)) {
        for (const id of chunk.type === 'chunk' ? Object.keys(chunk.modules) : []) {
          const path = id.split('?')[0];
          if (!path.startsWith(SRC + '/')) {
            continue;
          }
          const name = path.slice(SRC.length + 1);
          if (LOCAL.some((pattern) => pattern.test(name))) {
            this.error(`${entry} reaches ${name}, a module of the app's own scripts: an online page never holds it.`);
          }
          if (!graph.has(path)) {
            this.error(`${entry} bundles ${name}, which its import graph missed: its styles and texts would be left out.`);
          }
        }
      }
    },
  };
}
