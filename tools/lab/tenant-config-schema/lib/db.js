'use strict';
// Connections for the lab. The superuser password is read from a file outside
// the repository; the four lab roles get fresh random passwords on every run,
// held only in this process's memory.

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { Client } = require('pg');

const CONTAINER = 'cfgschema-pg';
const ROLES = ['cfg_owner', 'ns_operator', 'ns_tenant_admin', 'ns_api'];

function assertContainerRunning (port) {
  let out;
  try {
    out = execFileSync('docker', ['inspect', '-f', '{{.State.Running}} {{json .NetworkSettings.Ports}}', CONTAINER], { encoding: 'utf8' });
  } catch (e) {
    throw new Error(`container ${CONTAINER} is not present; start it as the README says`);
  }
  if (!out.startsWith('true ')) throw new Error(`container ${CONTAINER} is not running`);
  if (!out.includes(`"HostIp":"127.0.0.1","HostPort":"${port}"`)) {
    throw new Error(`container ${CONTAINER} is not published on 127.0.0.1:${port}: ${out.trim()}`);
  }
}

class Lab {
  constructor ({ port, secretsDir }) {
    this.host = '127.0.0.1';
    this.port = port;
    const pwFile = path.join(secretsDir, 'pg-superuser-password');
    this.superPassword = fs.readFileSync(pwFile, 'utf8').trim();
    this.passwords = {};
  }

  client (role, database) {
    const user = role === 'superuser' ? 'postgres' : role;
    const password = role === 'superuser' ? this.superPassword : this.passwords[role];
    return new Client({ host: this.host, port: this.port, user, password, database });
  }

  async super (database, fn) {
    const c = this.client('superuser', database || 'postgres');
    await c.connect();
    try { return await fn(c); } finally { await c.end(); }
  }

  async init () {
    const sql = fs.readFileSync(path.join(__dirname, '..', 'bootstrap', 'roles.sql'), 'utf8');
    await this.super('postgres', async (c) => {
      await c.query(sql);
      for (const r of ROLES) {
        this.passwords[r] = crypto.randomBytes(24).toString('base64url');
        // format() quotes the literal; the password never touches a file or a log
        await c.query(`DO $$ BEGIN EXECUTE format('ALTER ROLE %I PASSWORD %L', '${r}', '${this.passwords[r]}'); END $$`);
      }
    });
  }

  async createDb (name, template) {
    await this.super('postgres', async (c) => {
      await c.query(`DROP DATABASE IF EXISTS "${name}" WITH (FORCE)`);
      await c.query(`CREATE DATABASE "${name}" OWNER cfg_owner${template ? ` TEMPLATE "${template}"` : ''}`);
    });
  }

  async dropDb (name) {
    await this.super('postgres', (c) => c.query(`DROP DATABASE IF EXISTS "${name}" WITH (FORCE)`));
  }

  // Run fn(client) as `role` in one transaction, with the tenant bound
  // transaction-locally (the seam's asTenant shape). tenant null = unbound.
  async as (role, database, tenant, fn) {
    const c = this.client(role, database);
    await c.connect();
    try {
      await c.query('BEGIN');
      if (tenant) await c.query("SELECT set_config('app.current_tenant_id', $1, true)", [tenant]);
      const out = await fn(c);
      await c.query('COMMIT');
      return out;
    } catch (e) {
      await c.query('ROLLBACK').catch(() => {});
      throw e;
    } finally {
      await c.end();
    }
  }

  async connect (role, database) {
    const c = this.client(role, database);
    await c.connect();
    return c;
  }
}

module.exports = { Lab, assertContainerRunning, CONTAINER, ROLES };
