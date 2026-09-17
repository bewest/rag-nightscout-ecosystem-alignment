const root = process.argv[2];
process.env.ENABLE = process.argv[3];
const env = require(root + '/lib/server/env')();
const ctx = { settings: env.settings, language: {translate:s=>s}, moment: require(root+'/node_modules/moment'), levels: require(root+'/lib/levels') };
const plugins = require(root + '/lib/plugins')(ctx).registerServerDefaults();
console.log(root.split('/').pop(), 'ENABLE="'+process.argv[3]+'" enabled:', plugins.enabledPlugins ? '' : '', plugins.enabledPluginNames ? plugins.enabledPluginNames() : '');
