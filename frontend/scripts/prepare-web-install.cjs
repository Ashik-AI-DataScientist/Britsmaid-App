// Expo's single-page export uses its own HTML shell rather than app/+html.tsx.
// Add installation metadata to the exported shell, before validating/deploying it.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(process.argv[2] || 'dist');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.webmanifest'), 'utf8'));
assert.equal(manifest.name, 'Britsmaid');
assert.match(manifest.theme_color, /^#[\da-f]{6}$/i);
const target = path.join(root, 'index.html');
let document = fs.readFileSync(target, 'utf8');
assert.match(document, /<head>/);
assert.match(document, /<\/head>/);
document = document.replace(/<!-- Britsmaid home-screen metadata -->[\s\S]*?<!-- End Britsmaid home-screen metadata -->\s*/g, '');
document = document.replace(/<meta\b[^>]*name="viewport"[^>]*>/i, '<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover">');
const metadata = `<!-- Britsmaid home-screen metadata -->
<meta name="application-name" content="Britsmaid">
<meta name="description" content="Your Britsmaid property management workspace for owners, cleaners, supervisors and administrators.">
<meta name="theme-color" content="${manifest.theme_color}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Britsmaid">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" sizes="180x180" href="/icons/britsmaid-180-v1.png">
<!-- End Britsmaid home-screen metadata -->
`;
document = document.replace('</head>', metadata + '</head>');
fs.writeFileSync(target, document);
console.log('Prepared Britsmaid home-screen metadata in the single-page web export.');
