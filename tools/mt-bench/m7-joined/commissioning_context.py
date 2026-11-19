"""Build the SQL observation contract from the running roles' public settings."""
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def completion(evaluator, realtime, pair, image, instrument):
    binding = {'kind':'evaluator-work-v2', 'pair':pair, 'imageId':image, 'instrument':instrument}
    code = ("const o=require(process.argv[1]),fs=require('node:fs');"
            "const [e,r,b]=JSON.parse(fs.readFileSync(0));console.log(JSON.stringify(o.source(e,r,b)));")
    return json.loads(subprocess.check_output(['node', '-e', code, HERE/'completed-oracle.cjs'],
                      input=json.dumps([evaluator, realtime, binding]).encode(), timeout=10))


def sql_logins(evaluator, realtime):
    stream = evaluator['streamRole']
    roles = set(evaluator['sqlRoles']) | set(realtime['sqlRoles'])
    if stream not in evaluator['sqlRoles'] or stream in realtime['sqlRoles'] or len(roles) < 2:
        raise ValueError('M7_SQL_RECOVERY_IDENTITY')
    return {'pgstream':[], 'shared':[stream], 'adapter':sorted(roles - {stream})}
