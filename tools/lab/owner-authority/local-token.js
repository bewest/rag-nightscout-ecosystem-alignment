'use strict';

// The lab consumes the application verifier; its original prototype is retained
// in the instrument commit named by the immutable November 5 measurement.
const path = require('node:path');
if (!process.env.CRM_WORKTREE) throw new Error('CRM_WORKTREE must select the application verifier');
module.exports = require(path.resolve(process.env.CRM_WORKTREE, 'lib/tenant-authorization/access-token.js'));
