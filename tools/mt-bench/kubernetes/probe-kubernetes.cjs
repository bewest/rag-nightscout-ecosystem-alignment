'use strict';

module.exports = function kubernetes({args,fs,path,signalDir,execFile,process}) {
  if(args.restart !== '0' || !process.env.M7_COMPLETION_SOURCE) throw Error('K8S_PROBE_BOUNDARY');
  const psqlAsync = sql => new Promise((resolve,reject)=>{
    const began=performance.now();
    const child=execFile(process.env.K8S_PYTHON,[process.env.K8S_ADAPTER,'clinical-sql',process.env.K8S_RUN_DIRECTORY],
      {encoding:'utf8',timeout:60000,maxBuffer:32<<20},(err,stdout,stderr)=>{
        if(!err)return resolve(stdout);
        const nodeErrorCode=typeof err.code==='string'&&/^ERR_[A-Z_]{1,80}$/.test(err.code)?err.code:null;
        const value={version:1,verdict:'UNMEASURED',code:'M7_PROBE_SQL_OBSERVATION_UNAVAILABLE',
          reason:nodeErrorCode==='ERR_CHILD_PROCESS_STDIO_MAXBUFFER'?'OUTPUT_BOUND':err.killed?'TIMEOUT':'CHILD_EXIT',
          exitCode:Number.isInteger(err.code)?err.code:null,nodeErrorCode,
          signal:typeof err.signal==='string'&&/^[A-Z0-9]{1,24}$/.test(err.signal)?err.signal:null,
          timeoutMs:60000,wallMs:performance.now()-began,
          stdoutBytes:Buffer.byteLength(stdout||''),stderrBytes:Buffer.byteLength(stderr||''),
          childReportedCodes:[...new Set((stderr||'').match(/\b(?:K8S|M7)_[A-Z_]{1,88}\b/g)||[])].slice(0,16)};
        // The first transport failure is evidence; later callbacks cannot replace it.
        // A diagnostic write failure must never turn the failed read into success.
        try{fs.writeFileSync(path.join(signalDir,'sql-observation-failure.json'),
          JSON.stringify(value)+'\n',{mode:0o600,flag:'wx'});}catch{}
        reject(Error(value.code));
      });
    child.stdin.end(sql);
  });
  return {psqlAsync, frames: {rows:[],overflow:false}};
};
