#!/usr/bin/env python3
"""Native D6 transport/privilege discriminators. Owns only its named container."""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import time
import uuid

IMAGE = 'postgres@sha256:5db6dac2ef5dcff512f4f00a009c3c332b9f2f28f24277175bf3e4a3d02ef83a'
TENANT_A = '00000000-0000-4000-8000-000000000001'
TENANT_B = '00000000-0000-4000-8000-000000000002'
SETUP = r'''
CREATE ROLE tenant_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOREPLICATION;
CREATE ROLE reader_owner NOLOGIN NOSUPERUSER NOBYPASSRLS REPLICATION;
CREATE ROLE feed_login LOGIN NOSUPERUSER NOBYPASSRLS NOREPLICATION;
CREATE ROLE serving LOGIN NOSUPERUSER NOBYPASSRLS NOREPLICATION;
CREATE SCHEMA clock AUTHORIZATION tenant_owner;
CREATE TABLE clock.tenant_write_clock(tenant_id uuid PRIMARY KEY, last_stamp bigint NOT NULL);
ALTER TABLE clock.tenant_write_clock OWNER TO tenant_owner;
ALTER TABLE clock.tenant_write_clock ENABLE ROW LEVEL SECURITY;
ALTER TABLE clock.tenant_write_clock FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_clock ON clock.tenant_write_clock USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),'')::uuid);
GRANT USAGE ON SCHEMA clock TO serving, reader_owner;
GRANT SELECT ON clock.tenant_write_clock TO serving, reader_owner;
CREATE SCHEMA control AUTHORIZATION tenant_owner;
CREATE TABLE control.tenant_activity(tenant_id uuid PRIMARY KEY, version bigint NOT NULL, paused boolean NOT NULL, suspended boolean NOT NULL);
ALTER TABLE control.tenant_activity OWNER TO tenant_owner;
ALTER TABLE control.tenant_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE control.tenant_activity FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_activity ON control.tenant_activity USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),'')::uuid);
GRANT USAGE ON SCHEMA control TO serving, reader_owner;
GRANT SELECT ON control.tenant_activity TO serving, reader_owner;
CREATE TABLE public.excluded(secret_marker text);
CREATE PUBLICATION d6_metadata FOR TABLE clock.tenant_write_clock, control.tenant_activity WITH (publish='insert,update,delete');
CREATE PUBLICATION d6_wrong FOR TABLE public.excluded;
SELECT slot_name FROM pg_create_logical_replication_slot('d6_fixed','pgoutput');
SELECT slot_name FROM pg_create_logical_replication_slot('d6_other','pgoutput');
CREATE SCHEMA feed;
GRANT USAGE ON SCHEMA feed TO feed_login;
CREATE FUNCTION feed.peek(target integer) RETURNS TABLE(lsn pg_lsn,xid xid,data bytea)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE emitted bigint;
BEGIN
 IF target < 1 OR target > 100 THEN RAISE EXCEPTION 'D6_TARGET_REFUSED'; END IF;
 RETURN QUERY SELECT * FROM pg_logical_slot_peek_binary_changes('d6_fixed',NULL,target,'proto_version','1','publication_names','d6_metadata');
 GET DIAGNOSTICS emitted = ROW_COUNT;
 PERFORM set_config('d6.decoded_rows',emitted::text,false);
END $fn$;
ALTER FUNCTION feed.peek(integer) OWNER TO reader_owner;
REVOKE ALL ON FUNCTION feed.peek(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION feed.peek(integer) TO feed_login;
CREATE FUNCTION feed.advance(upto pg_lsn) RETURNS pg_lsn
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $fn$
DECLARE result pg_lsn;
BEGIN
 SELECT end_lsn INTO result FROM pg_replication_slot_advance('d6_fixed',upto);
 RETURN result;
END $fn$;
ALTER FUNCTION feed.advance(pg_lsn) OWNER TO reader_owner;
REVOKE ALL ON FUNCTION feed.advance(pg_lsn) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION feed.advance(pg_lsn) TO feed_login;
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--worktree', required=True)
    args = parser.parse_args()
    out = pathlib.Path(args.out).resolve()
    if out.exists():
        raise SystemExit('Refusing to overwrite a captured record')
    source = subprocess.check_output(['git', '-C', args.worktree, 'rev-parse', 'HEAD'], text=True).strip()
    if subprocess.check_output(['git', '-C', args.worktree, 'status', '--porcelain'], text=True).strip():
        raise SystemExit('Source worktree must be clean')
    name = 'ns-d6-proof-' + uuid.uuid4().hex[:12]
    results = {'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_head': source,
               'image': IMAGE, 'harness_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
               'container': name, 'cases': [], 'scope': 'Native PostgreSQL proof; no shipping reader implementation'}
    def call(command, *, data=None, timeout=60):
        return subprocess.run(command, input=data, text=True, capture_output=True, timeout=timeout)
    def sql(label, query, role='postgres', expect=0):
        start = time.monotonic()
        login = 'postgres' if role == 'reader_owner' else role
        if role == 'reader_owner':
            query = 'SET ROLE reader_owner;\n' + query
        p = call(['docker','exec','-i',name,'psql','-X','-q','-A','-t','-v','ON_ERROR_STOP=1','-v','VERBOSITY=verbose',
                  '-U',login,'-d','d6_test'], data=query)
        case = {'name': label, 'role': role, 'exit': p.returncode, 'stdout': p.stdout.strip(),
                'stderr': p.stderr.strip(), 'elapsed_ms': round((time.monotonic()-start)*1000,3),
                'expectation': 'success' if expect == 0 else 'semantic refusal',
                'matched_expected_exit': (p.returncode == 0) if expect == 0 else (p.returncode != 0)}
        results['cases'].append(case)
        print(json.dumps(case), flush=True)
        return case
    created = False
    try:
        p = call(['docker','run','--detach','--name',name,'--network','none','--label','nightscout.proof=d6-native',
                  '-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=d6_test',IMAGE,
                  '-c','wal_level=logical','-c','max_replication_slots=4','-c','max_wal_senders=4',
                  '-c','max_slot_wal_keep_size=256MB','-c','log_min_messages=warning'])
        if p.returncode:
            raise RuntimeError(p.stderr)
        created = True
        for _ in range(60):
            p = call(['docker','exec',name,'pg_isready','-h','127.0.0.1','-U','postgres','-d','d6_test'])
            if p.returncode == 0:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('Owned PostgreSQL did not become ready')
        sql('version', 'SELECT version(); SHOW wal_level;')
        setup = sql('setup', SETUP)
        if setup['exit']:
            raise RuntimeError('Setup failure; no discriminator measurement')
        sql('seed_two_tenants_and_excluded', f"INSERT INTO clock.tenant_write_clock VALUES ('{TENANT_A}',1),('{TENANT_B}',1); INSERT INTO control.tenant_activity VALUES ('{TENANT_A}',1,false,false),('{TENANT_B}',1,false,false); INSERT INTO public.excluded VALUES ('SYNTHETIC_EXCLUDED_MARKER');")
        sql('serving_bound_a_sees_only_a', f"BEGIN; SET LOCAL app.current_tenant_id='{TENANT_A}'; SELECT tenant_id FROM clock.tenant_write_clock ORDER BY tenant_id; COMMIT;", 'serving')
        sql('serving_unbound_sees_nothing', 'SELECT count(*) FROM clock.tenant_write_clock;', 'serving')
        sql('serving_raw_slot_refused', "SELECT * FROM pg_logical_slot_peek_binary_changes('d6_fixed',NULL,1,'proto_version','1','publication_names','d6_metadata');", 'serving', expect=1)
        sql('feed_raw_slot_refused', "SELECT * FROM pg_logical_slot_peek_binary_changes('d6_other',NULL,1,'proto_version','1','publication_names','d6_wrong');", 'feed_login', expect=1)
        sql('serving_wrapper_refused', 'SELECT count(*) FROM feed.peek(1);', 'serving', expect=1)
        sql('feed_cannot_assume_reader_owner', 'SET ROLE reader_owner;', 'feed_login', expect=1)
        sql('feed_direct_other_slot_advance_refused', "SELECT * FROM pg_replication_slot_advance('d6_other',pg_current_wal_lsn());", 'feed_login', expect=1)
        sql('reader_owner_unbound_sql_sees_nothing', 'SELECT count(*) FROM clock.tenant_write_clock;', 'reader_owner')
        sql('wrapper_peek_force_rls', "SELECT count(*),sum(octet_length(data)),string_agg(DISTINCT chr(get_byte(data,0)),',' ORDER BY chr(get_byte(data,0))) FROM feed.peek(1);", 'feed_login')
        sql('wrapper_peek_full', "SELECT count(*),sum(octet_length(data)),bool_or(position(convert_to('SYNTHETIC_EXCLUDED_MARKER','UTF8') in data)>0) FROM feed.peek(100);", 'feed_login')
        sql('wrapper_cross_tenant_metadata', f"SELECT bool_or(position(convert_to('{TENANT_A}','UTF8') in data)>0),bool_or(position(convert_to('{TENANT_B}','UTF8') in data)>0),bool_or(position(convert_to('SYNTHETIC_EXCLUDED_MARKER','UTF8') in data)>0) FROM feed.peek(100);", 'feed_login')
        sql('wrapper_fixed_slot_signature_refuses_other', "SELECT * FROM feed.peek('d6_other',1);", 'feed_login', expect=1)
        sql('wrapper_fixed_publication_signature_refuses_other', "SELECT * FROM feed.peek(1,'d6_wrong');", 'feed_login', expect=1)
        sql('wrapper_target_bound', 'SELECT * FROM feed.peek(101);', 'feed_login', expect=1)
        sql('feed_cannot_change_wrapper_owner', 'ALTER FUNCTION feed.peek(integer) OWNER TO feed_login;', 'feed_login', expect=1)
        sql('feed_cannot_mutate_publication', 'ALTER PUBLICATION d6_metadata ADD TABLE public.excluded;', 'feed_login', expect=1)
        sql('control_relax_rls', 'ALTER POLICY tenant_clock ON clock.tenant_write_clock USING (true);')
        sql('control_serving_bound_a_now_leaks_b', f"BEGIN; SET LOCAL app.current_tenant_id='{TENANT_A}'; SELECT tenant_id FROM clock.tenant_write_clock ORDER BY tenant_id; COMMIT;", 'serving')
        sql('restore_rls_policy', "ALTER POLICY tenant_clock ON clock.tenant_write_clock USING (tenant_id = nullif(current_setting('app.current_tenant_id',true),'')::uuid);")
        sql('restored_serving_bound_a_sees_only_a', f"BEGIN; SET LOCAL app.current_tenant_id='{TENANT_A}'; SELECT tenant_id FROM clock.tenant_write_clock ORDER BY tenant_id; COMMIT;", 'serving')
        sql('control_add_excluded_publication_table', "ALTER PUBLICATION d6_metadata ADD TABLE public.excluded; INSERT INTO public.excluded VALUES ('SYNTHETIC_CONTROL_LEAK');")
        sql('control_publication_leak_detected', "SELECT bool_or(position(convert_to('SYNTHETIC_CONTROL_LEAK','UTF8') in data)>0) FROM feed.peek(100);", 'feed_login')
        sql('restore_publication_membership', "ALTER PUBLICATION d6_metadata DROP TABLE public.excluded; INSERT INTO public.excluded VALUES ('SYNTHETIC_RESTORED_EXCLUDED');")
        sql('historical_published_row_still_replays', "SELECT bool_or(position(convert_to('SYNTHETIC_CONTROL_LEAK','UTF8') in data)>0) FROM feed.peek(100);", 'feed_login')
        sql('restored_publication_no_leak', "SELECT bool_or(position(convert_to('SYNTHETIC_RESTORED_EXCLUDED','UTF8') in data)>0) FROM feed.peek(100);", 'feed_login')
        sql('advance_seed', "SELECT feed.advance(pg_current_wal_lsn());", 'feed_login')
        sql('large_transaction_write', f"BEGIN; INSERT INTO clock.tenant_write_clock SELECT ('10000000-0000-4000-8000-'||lpad(to_hex(i),12,'0'))::uuid, i FROM generate_series(1,5000) i; COMMIT;")
        sql('large_transaction_peek_target_one', "SELECT count(*),sum(octet_length(data)),count(*) FILTER (WHERE get_byte(data,0)=73),count(*) FILTER (WHERE get_byte(data,0)=67) FROM feed.peek(1);", 'feed_login')
        sql('large_transaction_peek_repeat', "SELECT count(*),sum(octet_length(data)),count(*) FILTER (WHERE get_byte(data,0)=73),count(*) FILTER (WHERE get_byte(data,0)=67) FROM feed.peek(1);", 'feed_login')
        sql('large_transaction_limit_is_output_only', "SELECT count(*),sum(octet_length(data)) FROM (SELECT data FROM feed.peek(1) LIMIT 1) q; SELECT current_setting('d6.decoded_rows');", 'feed_login')
        sql('advance_complete_transaction', 'SELECT feed.advance(max(lsn)) FROM feed.peek(1);', 'feed_login')
        sql('after_advance_no_replay', 'SELECT count(*) FROM feed.peek(1);', 'feed_login')
        sql('restore_force_rls_preserved', "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid IN ('clock.tenant_write_clock'::regclass,'control.tenant_activity'::regclass) ORDER BY relname;")
        by_name = {case['name']: case for case in results['cases']}
        expected = {
            'serving_bound_a_sees_only_a': TENANT_A, 'serving_unbound_sees_nothing': '0',
            'reader_owner_unbound_sql_sees_nothing': '0', 'wrapper_cross_tenant_metadata': 't|t|f',
            'control_serving_bound_a_now_leaks_b': TENANT_A+'\n'+TENANT_B,
            'restored_serving_bound_a_sees_only_a': TENANT_A, 'control_publication_leak_detected': 't',
            'restored_publication_no_leak': 'f', 'historical_published_row_still_replays': 't',
            'large_transaction_peek_target_one': '5003|289012|5000|1',
            'large_transaction_peek_repeat': '5003|289012|5000|1',
            'large_transaction_limit_is_output_only': '1|21\n5003', 'after_advance_no_replay': '0',
            'restore_force_rls_preserved': 'tenant_activity|t|t\ntenant_write_clock|t|t'}
        results['assertions'] = {label: by_name[label]['stdout'] == value for label,value in expected.items()}
        results['assertions']['all_expected_exits'] = all(case['matched_expected_exit'] for case in results['cases'])
        for label in ['serving_raw_slot_refused','feed_raw_slot_refused','serving_wrapper_refused',
                      'feed_cannot_assume_reader_owner','feed_direct_other_slot_advance_refused',
                      'feed_cannot_change_wrapper_owner','feed_cannot_mutate_publication']:
            results['assertions'][label+'_sqlstate'] = '42501' in by_name[label]['stderr']
        results['verdict'] = 'PASS' if all(results['assertions'].values()) else 'FAIL'
        print(json.dumps({'verdict': results['verdict'], 'assertions': results['assertions']}), flush=True)
        results['unimplemented_checks'] = ['Runtime pin of wrapper body/owner/publication membership; mutation refusal above measures SQL privilege only',
            'Bounded bytes/memory/time during decode; SQL target does not promise a hard row bound',
            'Notification-before-advance crash protocol and actual reader/listener integration',
            'Shipping restore/epoch suites and pgoutput catalog invalidation']
        if results['verdict'] != 'PASS':
            raise RuntimeError('Native discriminator assertion failed')
    finally:
        if created:
            p = call(['docker','rm','--force','--volumes',name])
            results['cleanup'] = {'exit': p.returncode, 'stderr': p.stderr.strip()}
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2)+'\n')

if __name__ == '__main__':
    main()
