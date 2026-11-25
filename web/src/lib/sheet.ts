import sheet from '@/index.css?inline';

/** The styles of every screen, the app's ones included, for the app's own scripts (review-app.js, app.js): the online pages'
 * stylesheet holds only what their code uses, so that a change of the app's screens never changes it. Once a page, right
 * after the page's own stylesheet: before it, the page's utilities would win over the app's of the same layer (a dialog's
 * `sm:max-w-lg` under its `max-w-[calc(100%-2rem)]`); after the club's colours (`applyTheme`), its default ones would win
 * over them. */
export function addSheet() {
  if (!document.getElementById('app-sheet')) {
    const style = document.createElement('style');
    style.id = 'app-sheet';
    style.textContent = sheet;
    const links = document.head.querySelectorAll('link[rel=stylesheet]');
    if (links.length) {
      links[links.length - 1].after(style);
    } else {
      document.head.prepend(style);
    }
  }
}
