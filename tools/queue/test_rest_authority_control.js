'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const disable = require('./gates/_rest-authority-control');
const call = receiver => 'await ' + receiver + '.authorize({ tenant, principal, permission })';
const source = receiver => Array(4).fill(call(receiver)).join(';\n');

for (const receiver of ['authority', 'currentAuthority']) {
  test('disables all four ' + receiver + ' permission checks only', () => {
    const untouched = 'authority.subjectSnapshot({ tenant, principal }); accessTokens.authenticate({ token, tenant });';
    assert.equal(disable(source(receiver) + ';' + untouched), 'true;\ntrue;\ntrue;\ntrue;' + untouched);
  });
}
for (const [name, input] of [
  ['missing boundary', ''],
  ['partial boundary', Array(3).fill(call('currentAuthority')).join(';')],
  ['extra boundary', Array(5).fill(call('currentAuthority')).join(';')],
  ['mixed receivers', source('currentAuthority') + ';' + call('authority')],
  ['changed extra boundary', source('currentAuthority') + ';await currentAuthority.authorize({ permission })'],
  ['changed formatting', source('currentAuthority').replace('await currentAuthority.authorize', 'await currentAuthority .authorize')]
]) {
  test('refuses ' + name, () => assert.throws(() => disable(input), /CONTROL-INVALID/));
}
