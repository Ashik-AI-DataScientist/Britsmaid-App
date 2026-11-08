/** Print the generated document, never the React Native web application screen. */
export async function previewWebPdf(html: string): Promise<void> {
  document.getElementById('britsmaid-pdf-preview')?.remove();
  const previousFocus = document.activeElement as HTMLElement | null;
  const overlay = document.createElement('div');
  overlay.id = 'britsmaid-pdf-preview';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', 'PDF preview');
  overlay.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:#e8edf4;display:flex;flex-direction:column';
  const toolbar = document.createElement('div');
  toolbar.style.cssText = 'display:flex;align-items:center;flex-wrap:wrap;gap:12px;padding:12px;background:#19365c;color:white;font:14px Arial,sans-serif';
  const title = document.createElement('span');
  title.textContent = 'PDF preview — choose Save as PDF in the print dialog';
  title.style.flex = '1';
  const print = document.createElement('button');
  print.textContent = 'Print / Save PDF';
  print.disabled = true;
  const close = document.createElement('button');
  close.textContent = 'Close preview';
  for (const button of [print, close]) {
    button.style.cssText = 'padding:10px 16px;border:1px solid #c9d4e4;border-radius:6px;background:white;color:#19365c;font:bold 14px Arial,sans-serif;cursor:pointer';
  }
  const frame = document.createElement('iframe');
  frame.title = 'Britsmaid PDF document';
  frame.setAttribute('sandbox', 'allow-same-origin allow-modals');
  frame.style.cssText = 'flex:1;width:100%;border:0;background:white';
  let closed = false;
  let finish = () => {};
  const dismiss = () => { closed = true; finish(); overlay.remove(); previousFocus?.focus(); };
  close.onclick = dismiss;
  overlay.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') dismiss();
    if (event.key === 'Tab' && (document.activeElement === close && !event.shiftKey)) {
      event.preventDefault(); print.focus();
    } else if (event.key === 'Tab' && document.activeElement === print && event.shiftKey) {
      event.preventDefault(); close.focus();
    }
  });
  print.onclick = () => {
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
  };
  toolbar.append(title, print, close);
  overlay.append(toolbar, frame);
  // Install the load listener before attaching srcdoc: cached images may load immediately.
  const ready = new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('PDF preview took too long to load. Check your connection and try again.'));
      dismiss();
    }, 20000);
    finish = () => { clearTimeout(timeout); resolve(); };
    frame.onload = async () => {
      try {
        const doc = frame.contentDocument;
        if (!doc) throw new Error('Could not open PDF preview. Please try again.');
        await doc.fonts?.ready;
        if (closed) return;
        print.disabled = false;
        print.focus();
        finish();
      } catch (error) { reject(error); dismiss(); }
    };
    frame.onerror = () => { reject(new Error('Could not load PDF preview. Please try again.')); dismiss(); };
  });
  frame.srcdoc = html;
  document.body.append(overlay);
  await ready;
}
