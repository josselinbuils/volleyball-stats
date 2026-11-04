import type { ListedMatch } from '@/components/Matches';
import type { Data } from '@/lib/match';

const loaded = new Map<string, Promise<Data>>();
let queue: Promise<unknown> = Promise.resolve();

function read(m: ListedMatch): Promise<Data> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `${m.path.replace(/\/?$/, '/')}data.js${m.v ? `?v=${m.v}` : ''}`;
    script.onload = () => {
      script.remove();
      resolve(window.MATCH);
    };
    script.onerror = () => {
      script.remove();
      reject(new Error(`data.js of ${m.path}`));
    };
    document.head.append(script);
  });
}

/** A listed match's data.js, once. By script, to work from file://; one at a time, each writing the same `window.MATCH`. */
export function loadMatch(m: ListedMatch): Promise<Data> {
  const known = loaded.get(m.path);
  if (known) {
    return known;
  }
  const data = queue.then(() => read(m));
  queue = data.catch(() => undefined);
  data.catch(() => loaded.delete(m.path));
  loaded.set(m.path, data);
  return data;
}
