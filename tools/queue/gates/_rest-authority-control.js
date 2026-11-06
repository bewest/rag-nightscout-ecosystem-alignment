'use strict';

// The four permission checks cover writes, reads and the two discovery loops.
// Recognize the historical receiver and the operation-local token authority,
// but refuse changed or mixed boundaries rather than partially disabling them.
module.exports = function disableCurrentAuthority (source) {
  const receivers = ['authority', 'currentAuthority'];
  const boundaries = receivers.map(receiver =>
    'await ' + receiver + '.authorize({ tenant, principal, permission })');
  const counts = boundaries.map(boundary => source.split(boundary).length - 1);
  const selected = counts.findIndex(count => count === 4);
  const calls = source.match(/await\s+(?:authority|currentAuthority)\s*\.\s*authorize\s*\(/g) || [];
  if (selected < 0 || counts.some((count, index) => index !== selected && count !== 0) || calls.length !== 4) {
    throw new Error('CONTROL-INVALID: expected exactly four unmixed current-authority permission boundaries; found ' + counts.join('/'));
  }
  return source.split(boundaries[selected]).join('true');
};
