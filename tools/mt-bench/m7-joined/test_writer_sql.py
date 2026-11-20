"""The writer-driven observer's own SQL on PostgreSQL, against synthetic typed rows.

Opt-in: set M7_WRITER_SQL_PG_CONTAINER to a disposable PostgreSQL container
(psql as postgres). Every case runs in one transaction that rolls back.
"""
import hashlib
import json
import os
import subprocess
import unittest

import accepted_inputs as inputs
import assessor

CONTAINER = os.environ.get('M7_WRITER_SQL_PG_CONTAINER')
TENANT = '11111111-1111-4111-8111-111111111111'
RUN = 'synthetic-sql'
CONFIG = {'kind': 'evaluator-work-v2', 'checkpoint': 'syn_checkpoint', 'entries': 'syn_entries', 'clock': 'syn_clock',
          'consumer': 'evaluator-syn-completed',
          'writerDriven': {'lifecycle': 'syn_control', 'devicestatus': 'syn_devicestatus', 'treatments': 'syn_treatments'}}
DIGEST = hashlib.sha256(json.dumps(['evaluator-work-v2', 'syn_checkpoint', 'evaluator-syn', *inputs.LIFECYCLE_CODEC],
                                   separators=(',', ':')).encode()).hexdigest()
HEX = 'a' * 64
MARK = "SELECT '--step--';"


def schema():
    ddl = ''.join(f'CREATE SCHEMA {name};\n' for name in
                  ('syn_clock', 'syn_control', 'syn_checkpoint', 'syn_entries', 'syn_devicestatus', 'syn_treatments'))
    ddl += ''.join(f'CREATE TABLE syn_{k}.{k} (tenant_id uuid, doc jsonb);\n' for k in ('entries', 'devicestatus', 'treatments'))
    return ddl + """
CREATE TABLE syn_clock.tenant_write_clock (tenant_id uuid, last_stamp bigint);
CREATE TABLE syn_control.tenant_lifecycle_windows (tenant_id uuid, generation bigint, phase text);
CREATE TABLE syn_checkpoint.tenant_consumer_checkpoint (tenant_id uuid, consumer text, checkpoint bigint,
  work_observed bigint[], work_completed bigint[], work_version int, contract_digest text, work_enabled boolean,
  projection jsonb, output_revision bigint, output_identity text, output_digest text, output_restore_generation bigint);
"""


def completed_row(*, checkpoint, observed, completed, restore, result_generation, digest=DIGEST):
    output = {'tenant': TENANT, 'inputCheckpoint': checkpoint, 'checkpoint': checkpoint,
              'result': {'checkpoint': checkpoint, 'progress': 'level-window', 'generation': str(result_generation),
                         'properties': {}}, 'frame': {}}
    projection = json.dumps([{'kind': 'evaluator-work-v2', 'output': output}])
    return (f"INSERT INTO syn_checkpoint.tenant_consumer_checkpoint VALUES ('{TENANT}','{CONFIG['consumer']}',{checkpoint},"
            f"ARRAY[{observed},1,1,1,NULL,1],ARRAY[{completed},1,1,1,NULL,1],2,'{digest}',true,'{projection}',1,"
            f"'{HEX}','{HEX}',{restore});")


def run_case(generation, row_sql, *, sql_edit=None):
    """Baseline at `generation`, then one write at stamp 101 and the given -completed row."""
    baseline, sql = inputs.writer_queries(CONFIG, RUN)
    if sql_edit:
        sql = sql_edit(sql)
    write = json.dumps({'device': RUN, 'date': '7', 'srvModified': 101})
    script = '\n'.join([
        'BEGIN;', schema(),
        f"INSERT INTO syn_clock.tenant_write_clock VALUES ('{TENANT}',100);",
        f"INSERT INTO syn_control.tenant_lifecycle_windows VALUES ('{TENANT}',{generation},'active');",
        MARK, baseline,
        f"INSERT INTO syn_entries.entries VALUES ('{TENANT}','{write}');",
        f"UPDATE syn_clock.tenant_write_clock SET last_stamp=101;",
        row_sql, MARK, sql, 'ROLLBACK;'])
    out = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-X', '-q', '-At', '-v', 'ON_ERROR_STOP=1',
                          '-U', 'postgres'], input=script, capture_output=True, text=True, check=True).stdout
    blocks = out.split('--step--')
    value = inputs.WriterCoverage(RUN, [TENANT], 0)
    value.prime(json.loads(blocks[1].strip()))
    value.capture([json.loads(line) for line in blocks[2].splitlines() if line.strip()], 1, 2)
    ack = {(TENANT, 'entries', RUN, '7'): 1}
    return assessor.assess(value.events(ack, 200), [TENANT])['components']['clinical']['classifications']


@unittest.skipUnless(CONTAINER, 'set M7_WRITER_SQL_PG_CONTAINER to a disposable PostgreSQL container')
class WriterSQL(unittest.TestCase):
    def test_covered_when_completed_clock_reaches_the_observed_floor_at_the_tenant_generation(self):
        self.assertEqual(run_case(1, completed_row(checkpoint=101, observed=910, completed=910, restore=1,
                                                   result_generation=1)), {'ON_TIME': 1})

    def test_completed_clock_below_the_floor_is_not_covered(self):
        self.assertEqual(run_case(1, completed_row(checkpoint=101, observed=910, completed=909, restore=1,
                                                   result_generation=1)), {'UNMEASURED': 1})

    def test_output_from_a_stale_restore_generation_is_not_covered(self):
        self.assertEqual(run_case(2, completed_row(checkpoint=101, observed=910, completed=910, restore=1,
                                                   result_generation=2)), {'UNMEASURED': 1})

    def test_a_row_under_the_three_part_contract_is_not_covered(self):
        three = hashlib.sha256(json.dumps(['evaluator-work-v2', 'syn_checkpoint', 'evaluator-syn'],
                                          separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(run_case(1, completed_row(checkpoint=101, observed=910, completed=910, restore=1,
                                                   result_generation=1, digest=three)), {'UNMEASURED': 1})


if __name__ == '__main__':
    unittest.main()
