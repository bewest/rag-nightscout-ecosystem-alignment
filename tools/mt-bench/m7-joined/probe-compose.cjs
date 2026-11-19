'use strict';

module.exports = function compose({args,execFile,discovery,completionSource}) {
  const [project, envFile, ...composeFiles] = args.compose.split('|');
  const composeArgs = ['compose', '-p', project, '--env-file', envFile, ...composeFiles.flatMap(f => ['-f', f])];
  const psqlAsync = sql => new Promise((resolve,reject) => execFile('docker', [...composeArgs, 'exec', '-T', 'postgres', 'psql', '-X', '-At', '-F', '\t', '-U', 'postgres', '-d', 'nightscout_compose_test', '-c', sql],
    { encoding: 'utf8', timeout:5000, maxBuffer:64 << 20 }, (err, stdout) => err && discovery && completionSource ? reject(Error('M7_PROBE_SQL_OBSERVATION_UNAVAILABLE')) : resolve(err ? '' : stdout)));
  return {psqlAsync, composeArgs, docker: (...options) => execFile('docker', ...options)};
};
