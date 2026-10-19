const { getDefaultConfig } = require('expo/metro-config');
// Expo owns compatible cache/resolver defaults. A direct import of a transitive
// metro-cache package breaks clean pnpm native release builds.
const config = getDefaultConfig(__dirname);
config.maxWorkers = 2;
module.exports = config;
