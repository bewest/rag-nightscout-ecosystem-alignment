'use strict';
// Inspect module resolution in the process that will use it. No connection or
// socket constructor is invoked; ambient search-path fallbacks never earn credit.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),{createRequire}=require('node:module');
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function inspect(root,dependencyRoot,names){
 if(process.env.NODE_OPTIONS||process.env.NODE_PATH||process.env.LD_PRELOAD)throw Error('M7_DEPENDENCY_PRELOAD');
 root=fs.realpathSync(root);dependencyRoot=fs.realpathSync(dependencyRoot);
 const r=createRequire(path.join(root,'package.json')),lock=JSON.parse(fs.readFileSync(path.join(root,'package-lock.json'))),modules={};
 for(const name of names){
  if(!['pg','socket.io-client','js-yaml'].includes(name))throw Error('M7_DEPENDENCY_NAME');
  const entry=fs.realpathSync(r.resolve(name)),version=r(name+'/package.json').version;
  if(!entry.startsWith(dependencyRoot+path.sep))throw Error('M7_DEPENDENCY_CONTEXT');
  if(lock.packages?.['node_modules/'+name]?.version!==version)throw Error('M7_DEPENDENCY_LOCK_VERSION');
  const value=r(name);if(name==='pg'?(typeof value.Pool!=='function'||typeof value.Client!=='function'):name==='js-yaml'?typeof value.load!=='function':typeof value.io!=='function')throw Error('M7_DEPENDENCY_EXPORT');
  modules[name]={entry,version,entrySha256:hash(entry)};
 }
 return {root,dependencyRoot,cwd:process.cwd(),nodeBinary:fs.realpathSync(process.execPath),nodeVersion:process.version,packageSha256:hash(path.join(root,'package.json')),lockSha256:hash(path.join(root,'package-lock.json')),modules};
}
module.exports={inspect};
