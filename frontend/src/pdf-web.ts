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
  title.style.cssText = 'flex:1 1 100%;line-height:1.4';
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
  let releasePrint = () => {};
  const dismiss = () => { closed = true; finish(); releasePrint(); overlay.remove(); previousFocus?.focus(); };
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
    const doc = frame.contentDocument;
    if (!doc?.body || closed) return;
    releasePrint();
    // Print the report as normal top-level flow, never a fixed-height iframe.
    // Stay in this tab so mobile installation and pop-up settings do not matter.
    const printRoot = document.createElement('div');
    printRoot.id = 'britsmaid-print-document';
    printRoot.style.display = 'none';
    printRoot.innerHTML = doc.body.innerHTML;
    const printStyles = document.createElement('style');
    printStyles.media = 'print';
    printStyles.textContent = Array.from(doc.querySelectorAll('style')).map(style => style.textContent || '').join('\n') + `
      html,body{height:auto!important;min-height:0!important;overflow:visible!important;position:static!important;display:block!important}
      body>:not(#britsmaid-print-document){display:none!important}
      body>#britsmaid-print-document{display:block!important;position:static!important;height:auto!important;width:auto!important;overflow:visible!important}
    `;
    const originalTitle = document.title;
    const cleanup = () => {
      printRoot.remove(); printStyles.remove(); document.title = originalTitle;
      window.removeEventListener('afterprint', cleanup);
    };
    releasePrint = cleanup;
    document.head.append(printStyles);
    document.body.append(printRoot);
    document.title = doc.title || 'Britsmaid report';
    window.addEventListener('afterprint', cleanup, { once: true });
    try { window.focus(); window.print(); }
    catch { cleanup(); title.textContent = 'Could not open printing. Please try again.'; }
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
