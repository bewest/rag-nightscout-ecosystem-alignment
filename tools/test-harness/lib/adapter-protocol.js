'use strict';

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const Ajv = require('ajv');
const addFormats = require('ajv-formats');

const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);

const inputSchema = require('../contracts/adapter-input.schema.json');
const outputSchema = require('../contracts/adapter-output.schema.json');
const manifestSchema = require('../contracts/adapter-manifest.schema.json');

const validateInput = ajv.compile(inputSchema);
const validateOutput = ajv.compile(outputSchema);
const validateManifest = ajv.compile(manifestSchema);

/**
 * Load an adapter from a directory containing a manifest.json.
 * Returns { manifest, dir, invoke }.
 */
function loadAdapter(adapterDir) {
  const absDir = path.resolve(adapterDir);
  const manifestPath = path.join(absDir, 'manifest.json');

  if (!fs.existsSync(manifestPath)) {
    throw new Error(`No manifest.json found in ${absDir}`);
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

  if (!validateManifest(manifest)) {
    const errs = validateManifest.errors.map(e => `${e.instancePath} ${e.message}`).join('; ');
    throw new Error(`Invalid adapter manifest in ${absDir}: ${errs}`);
  }

  return {
    manifest,
    dir: absDir,
    invoke: (input, opts) => invokeAdapter(absDir, manifest, input, opts),
  };
}

/**
 * Discover all adapters in a parent directory.
 * Each subdirectory with a manifest.json is an adapter.
 */
function discoverAdapters(parentDir) {
  const absDir = path.resolve(parentDir);
  const adapters = [];

  for (const entry of fs.readdirSync(absDir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const candidatePath = path.join(absDir, entry.name);
    const manifestPath = path.join(candidatePath, 'manifest.json');
    if (fs.existsSync(manifestPath)) {
      try {
        adapters.push(loadAdapter(candidatePath));
      } catch (err) {
        console.error(`Warning: skipping adapter ${entry.name}: ${err.message}`);
      }
    }
  }

  return adapters;
}

/**
 * Invoke an adapter process via JSON-over-stdio.
 *
 * Modes:
 *   execute        — run algorithm, return normalized output
 *   validate-input — return the native input the adapter would construct
 *   describe       — return adapter capabilities without running
 *   batch          — execute multiple vectors in one process
 *
 * @param {string} adapterDir
 * @param {object} manifest
 * @param {object|object[]} input — adapter input (or array for batch mode)
 * @param {object} opts — { mode, verbose, timeout }
 * @returns {Promise<object>} adapter output
 */
function invokeAdapter(adapterDir, manifest, input, opts = {}) {
  const mode = opts.mode || 'execute';
  const verbose = opts.verbose || false;
  const timeout = opts.timeout || 30000;

  const payload = JSON.stringify({
    mode,
    verbose,
    input: Array.isArray(input) ? undefined : input,
    vectors: Array.isArray(input) ? input : undefined,
  });

  // Validate input against schema (skip for describe mode)
  if (mode !== 'describe' && !Array.isArray(input)) {
    if (!validateInput(input)) {
      const errs = validateInput.errors.map(e => `${e.instancePath} ${e.message}`).join('; ');
      return Promise.resolve({
        error: `Input validation failed: ${errs}`,
        validationErrors: validateInput.errors,
      });
    }
  }

  const cwd = manifest.invoke.cwd
    ? path.resolve(adapterDir, manifest.invoke.cwd)
    : adapterDir;

  const env = { ...process.env, ...(manifest.invoke.env || {}) };

  return new Promise((resolve, reject) => {
    const parts = manifest.invoke.command.split(' ');
    const cmd = parts[0];
    const args = parts.slice(1);

    const proc = spawn(cmd, args, { cwd, env, stdio: ['pipe', 'pipe', 'pipe'] });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', chunk => { stdout += chunk; });
    proc.stderr.on('data', chunk => { stderr += chunk; });

    const timer = setTimeout(() => {
      proc.kill('SIGTERM');
      reject(new Error(`Adapter ${manifest.name} timed out after ${timeout}ms`));
    }, timeout);

    proc.on('close', code => {
      clearTimeout(timer);

      if (code !== 0) {
        reject(new Error(`Adapter ${manifest.name} exited with code ${code}: ${stderr}`));
        return;
      }

      let result;
      try {
        result = JSON.parse(stdout);
      } catch (e) {
        reject(new Error(`Adapter ${manifest.name} returned invalid JSON: ${stdout.slice(0, 200)}`));
        return;
      }

      // Validate output against schema (for execute mode)
      if (mode === 'execute' && !result.error) {
        if (!validateOutput(result)) {
          result._outputValidationErrors = validateOutput.errors;
        }
      }

      resolve(result);
    });

    proc.on('error', err => {
      clearTimeout(timer);
      reject(new Error(`Failed to spawn adapter ${manifest.name}: ${err.message}`));
    });

    proc.stdin.write(payload);
    proc.stdin.end();
  });
}

/**
 * Run a single vector through an adapter and return structured result.
 */
async function runVector(adapter, vector, opts = {}) {
  const input = vectorToAdapterInput(vector);
  const startMs = Date.now();

  try {
    const output = await adapter.invoke(input, opts);
    const elapsedMs = Date.now() - startMs;

    return {
      vectorId: vector.metadata?.id || 'unknown',
      adapter: adapter.manifest.name,
      input,
      output,
      elapsedMs,
      error: output.error || null,
    };
  } catch (err) {
    return {
      vectorId: vector.metadata?.id || 'unknown',
      adapter: adapter.manifest.name,
      input,
      output: null,
      elapsedMs: Date.now() - startMs,
      error: err.message,
    };
  }
}

/**
 * Translate a conformance vector's input section to the adapter input contract.
 * The vector format is close to the adapter contract — this is intentionally thin.
 */
function vectorToAdapterInput(vector) {
  const vi = vector.input;
  return {
    clock: vi.glucoseStatus?.timestamp || new Date().toISOString(),
    glucoseStatus: vi.glucoseStatus || {},
    iob: vi.iob || { iob: 0 },
    profile: vi.profile || {},
    mealData: vi.mealData || {},
    currentTemp: vi.currentTemp || {},
    autosensData: vi.autosensData || { ratio: 1.0 },
    microBolusAllowed: vi.microBolusAllowed || false,
    flatBGsDetected: vi.flatBGsDetected || false,
    // Pass through extension fields if present
    ...(vi.glucoseHistory && { glucoseHistory: vi.glucoseHistory }),
    ...(vi.doseHistory && { doseHistory: vi.doseHistory }),
    ...(vi.carbHistory && { carbHistory: vi.carbHistory }),
    ...(vi.effectModifiers && { effectModifiers: vi.effectModifiers }),
  };
}

module.exports = {
  loadAdapter,
  discoverAdapters,
  invokeAdapter,
  runVector,
  vectorToAdapterInput,
  validateInput: (input) => {
    const valid = validateInput(input);
    return { valid, errors: valid ? [] : validateInput.errors };
  },
  validateOutput: (output) => {
    const valid = validateOutput(output);
    return { valid, errors: valid ? [] : validateOutput.errors };
  },
};
