/* global __dirname */
const fs = require('node:fs');
const path = require('node:path');
module.exports = ({ config }) => {
  const backend = process.env.EXPO_PUBLIC_BACKEND_URL || '';
  const lan = process.env.BRITSMAID_PREVIEW_LAN === '1';
  if (process.env.EAS_BUILD === 'true' && !backend) throw new Error('Set EXPO_PUBLIC_BACKEND_URL to the reachable staging backend before building.');
  if (backend) {
    const url = new URL(backend);
    if (['localhost','127.0.0.1','0.0.0.0','::1','[::1]'].includes(url.hostname)) throw new Error('A phone cannot reach the PC through localhost.');
    if (url.username || url.password || url.search || url.hash || (url.pathname !== '/' && url.pathname !== '')) throw new Error('Use the backend origin without credentials, paths or tokens.');
    if (url.protocol !== 'https:') {
      const privateIPv4 = /^(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(url.hostname);
      if (!lan || url.protocol !== 'http:' || !privateIPv4) throw new Error('Use HTTPS staging, or explicitly enable private-LAN preview.');
      config.plugins = [...config.plugins, ['./scripts/with-preview-network.cjs', { host:url.hostname }]];
    }
  }
  const metadata = path.join(__dirname, 'preview-source.json');
  const source = fs.existsSync(metadata) ? JSON.parse(fs.readFileSync(metadata,'utf8').replace(/^\uFEFF/,'')) : {};
  const projectId = process.env.BRITSMAID_EAS_PROJECT_ID;
  config.extra = { ...config.extra, previewSource: source, ...(projectId ? { eas:{projectId} } : {}) };
  return config;
};
