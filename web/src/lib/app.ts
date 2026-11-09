/** The app's text fields' look, as the review's. */
export const INPUT =
  'h-9 rounded-md border border-input bg-transparent px-2.5 text-base font-normal shadow-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive';

/** The answer of an /app/ request: its JSON, with `ok` false and the server's `error` when refused, or `error` "network"
 * (status 0) when no answer came: it never rejects, so no screen waits for good. */
export async function call<T = Record<string, unknown>>(path: string, body?: object): Promise<T & { ok: boolean; error?: string; status: number }> {
  let response: Response;
  try {
    response = await fetch(`/app/${path}`, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  } catch {
    return { ok: false, error: 'network', status: 0 } as T & { ok: boolean; error?: string; status: number };
  }
  let data = {} as T & { error?: string };
  try {
    data = await response.json();
  } catch {
    // Not JSON: a crash in the server.
  }
  return { ...data, ok: response.ok, status: response.status };
}
