export const APP_NAME = 'Volleyball Stats';

/** A page's title, the app's name after it in the app's own window: on the review server, on this machine. */
export function windowTitle(title: string, host = location.hostname): string {
  return host === '127.0.0.1' || host === 'localhost' ? `${title} – ${APP_NAME}` : title;
}
