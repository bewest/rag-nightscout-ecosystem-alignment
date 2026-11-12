'use strict';
const fs = require('node:fs'), path = require('node:path'), Module = require('node:module');
const target = path.resolve('lib/server/serve/evaluator-config.js'), original = Module._extensions['.js'];
const controls = {
  'parse-every-read': ['if (current === lastText) return lastParsed;', 'if (false) return lastParsed;'],
  'freeze-hot-bytes': ['const currentConfig = read;', 'const currentConfig = () => initial;']
};
const selected = controls[process.env.M7_EVALUATOR_COUNTER_CONTROL];
if (!selected) throw new Error('CONTROL_SELECTION_REQUIRED');
Module._extensions['.js'] = function (loaded, file) {
  if (file !== target) return original(loaded, file);
  const text = fs.readFileSync(file, 'utf8');
  if (text.split(selected[0]).length !== 2) throw new Error('CONTROL_SOURCE_MISMATCH');
  loaded._compile(text.replace(selected[0], selected[1]), file);
};
