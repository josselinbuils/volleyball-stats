import sheet from '@/index.css?inline';

/** The styles of every screen, the app's ones included, for the app's own scripts (review-app.js, app.js): the online pages'
 * stylesheet holds only what their code uses, so that a change of the app's screens never changes it. Once a page, first
 * in the head: after the club's colours (`applyTheme`), its default ones would win over them. */
export function addSheet() {
  if (!document.getElementById('app-sheet')) {
    const style = document.createElement('style');
    style.id = 'app-sheet';
    style.textContent = sheet;
    document.head.prepend(style);
  }
}
