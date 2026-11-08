/** Asks the review server to open the match `name`, then goes to its review once the server has restarted on it. */
export async function openMatch(name: string): Promise<void> {
  const response = await fetch('/open', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
  if (!response.ok) {
    throw new Error(`open: ${response.status}`);
  }
  await reachedMatch(name);
}

/** Brings the match `name` from the server, then shows the list again. */
export async function pullMatch(name: string): Promise<void> {
  const response = await fetch('/pull', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
  if (!response.ok) {
    throw new Error(`pull: ${response.status}`);
  }
  location.reload();
}

/** Reloads the page once the server, restarting on the same match, answers again. */
export async function restarted(): Promise<void> {
  // The server stops a moment after its answer.
  await new Promise((resolve) => setTimeout(resolve, 1500));
  const giveUp = Date.now() + 5 * 60_000;
  while (Date.now() < giveUp) {
    try {
      if ((await fetch('/current')).ok) {
        location.reload();
        return;
      }
    } catch {
      // Not listening yet.
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error('restart: timed out');
}

/** Goes to the review of the match `name`, keeping the tab, once the server has restarted on it. */
export async function reachedMatch(name: string): Promise<void> {
  const giveUp = Date.now() + 5 * 60_000;
  while (Date.now() < giveUp) {
    try {
      const current = (await (await fetch('/current')).json()) as { name: string | null };
      if (current.name === name) {
        // On /review, setting the same address with a hash would only scroll to it.
        if (location.pathname === '/review') {
          location.reload();
        } else {
          location.href = `/review${location.hash}`;
        }
        return;
      }
    } catch {
      // Not listening yet: the server is restarting.
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error('open: timed out');
}
