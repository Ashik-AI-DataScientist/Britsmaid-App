const { withAndroidManifest, withDangerousMod } = require('expo/config-plugins');
const fs = require('node:fs');
const path = require('node:path');
module.exports = function withPreviewNetwork(config, { host }) {
  // Only the selected private LAN address is allowed over HTTP in this preview binary.
  config = withAndroidManifest(config, c => {
    const app = c.modResults.manifest.application[0].$;
    app['android:networkSecurityConfig'] = '@xml/preview_network_security';
    app['android:usesCleartextTraffic'] = 'false';
    return c;
  });
  return withDangerousMod(config, ['android', async c => {
    const dir = path.join(c.modRequest.platformProjectRoot, 'app/src/main/res/xml');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'preview_network_security.xml'), `<?xml version="1.0" encoding="utf-8"?><network-security-config><base-config cleartextTrafficPermitted="false"/><domain-config cleartextTrafficPermitted="true"><domain includeSubdomains="false">${host}</domain></domain-config></network-security-config>`);
    return c;
  }]);
};
