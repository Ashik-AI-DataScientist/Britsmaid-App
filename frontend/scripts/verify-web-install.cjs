// Verify actual exported assets, not only source configuration.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(process.argv[2] || 'dist');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.webmanifest'), 'utf8'));
assert.equal(manifest.name, 'Britsmaid');
assert.equal(manifest.short_name, 'Britsmaid');
assert.equal(manifest.id, '/');
assert.equal(manifest.start_url, '/');
assert.equal(manifest.scope, '/');
assert.equal(manifest.display, 'standalone');
assert.ok(manifest.icons.some(i => i.sizes === '192x192' && i.purpose === 'any'));
assert.ok(manifest.icons.some(i => i.sizes === '512x512' && i.purpose === 'any'));
assert.ok(manifest.icons.some(i => i.purpose === 'maskable'));
for (const icon of manifest.icons) {
  assert.ok(/^\/icons\/[\w-]+\.png$/.test(icon.src));
  const bytes = fs.readFileSync(path.join(root, icon.src));
  assert.equal(bytes.subarray(1, 4).toString(), 'PNG');
  assert.equal(`${bytes.readUInt32BE(16)}x${bytes.readUInt32BE(20)}`, icon.sizes);
}
const apple = fs.readFileSync(path.join(root, 'icons/britsmaid-180-v1.png'));
assert.equal(apple.readUInt32BE(16), 180);
assert.equal(apple.readUInt32BE(20), 180);
for (const file of ['index.html', 'install.html']) {
  const document = fs.readFileSync(path.join(root, file), 'utf8');
  assert.match(document, /rel="manifest"[^>]*href="\/manifest\.webmanifest"/);
  assert.match(document, /rel="apple-touch-icon"[^>]*href="\/icons\/britsmaid-180-v1\.png"/);
  assert.match(document, /name="apple-mobile-web-app-title"[^>]*content="Britsmaid"/);
  assert.match(document, /name="apple-mobile-web-app-capable"[^>]*content="yes"/);
  assert.match(document, /viewport-fit=cover/);
  assert.doesNotMatch(document, /navigator\.serviceWorker\.register/);
}
assert.ok(fs.existsSync(path.join(root, 'favicon.ico')));
console.log('Branded web export: manifest, Android icons, iPhone touch icon, standalone metadata and static install page verified.');
