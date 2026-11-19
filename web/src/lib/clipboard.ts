/** Puts `text` on the clipboard; a page in plain http (the local network's) has no navigator.clipboard: a selected
 * text field copied the old way instead. Throws when neither copies. */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard) {
    return navigator.clipboard.writeText(text);
  }
  const field = document.createElement('textarea');
  field.value = text;
  field.setAttribute('readonly', '');
  field.style.position = 'fixed';
  field.style.opacity = '0';
  document.body.append(field);
  field.select();
  try {
    if (!document.execCommand('copy')) {
      throw new Error('copy');
    }
  } finally {
    field.remove();
  }
}
