/**
 * oref0 Conformance Test Runner
 * 
 * Executes conformance test vectors against the oref0 determine-basal algorithm.
 * 
 * Usage:
 *   node conformance/runners/oref0-runner.js [--vectors DIR] [--output FILE] [--quiet]
 */

'use strict';

const fs = require('fs');
const path = require('path');

// Paths
const WORKSPACE_ROOT = path.resolve(__dirname, '../..');
const OREF0_PATH = path.join(WORKSPACE_ROOT, 'externals/oref0');
const VECTORS_DIR = path.join(WORKSPACE_ROOT, 'conformance/vectors');
const DEFAULT_OUTPUT = path.join(WORKSPACE_ROOT, 'conformance/results/oref0-results.json');

// Console management - parse args early to set QUIET_MODE before requiring oref0
const originalConsoleError = console.error;
const originalConsoleLog = console.log;
let QUIET_MODE = process.argv.includes('--quiet') || process.argv.includes('-q');

function suppressConsole() {
    if (QUIET_MODE) {
        console.error = () => {};
        console.log = () => {};
    }
}
function restoreConsole() {
    console.error = originalConsoleError;
    console.log = originalConsoleLog;
}
function log(...args) {
    originalConsoleLog.apply(console, args);
}

// Suppress before loading oref0 (it logs during require)
suppressConsole();

// Load oref0 modules
let determine_basal, tempBasalFunctions;
try {
    determine_basal = require(path.join(OREF0_PATH, 'lib/determine-basal/determine-basal'));
    tempBasalFunctions = require(path.join(OREF0_PATH, 'lib/basal-set-temp'));
} catch (e) {
    restoreConsole();
    console.error('ERROR: Could not load oref0 modules from', OREF0_PATH);
    console.error('Run "make bootstrap" to clone external repos');
    process.exit(1);
}

restoreConsole();

/**
 * Transform conformance vector input to oref0 input format
 */
function vectorToOref0Input(vector) {
    const input = vector.input;
    
    // glucose_status
    const glucose_status = {
        glucose: input.glucoseStatus.glucose,
        delta: input.glucoseStatus.delta || 0,
        short_avgdelta: input.glucoseStatus.shortAvgDelta || 0,
        long_avgdelta: input.glucoseStatus.longAvgDelta || 0,
        date: input.glucoseStatus.timestamp ? new Date(input.glucoseStatus.timestamp).getTime() : Date.now(),
        noise: input.glucoseStatus.noise || 0
    };
    
    // currenttemp
    const currenttemp = {
        rate: input.currentTemp?.rate || 0,
        duration: input.currentTemp?.duration || 0,
        temp: 'absolute'
    };
    
    // iob_data - oref0 expects object, not array
    const iob_data = {
        iob: input.iob?.iob || 0,
        basaliob: input.iob?.basalIob || 0,
        bolussnooze: input.iob?.bolusIob || 0,
        activity: input.iob?.activity || 0,
        iobWithZeroTemp: input.iob?.iobWithZeroTemp || null
    };
    
    // profile
    const profile = {
        current_basal: input.profile?.basalRate || 1.0,
        sens: input.profile?.sensitivity || 50,
        carb_ratio: input.profile?.carbRatio || 10,
        min_bg: input.profile?.targetLow || 100,
        max_bg: input.profile?.targetHigh || 120,
        target_bg: (input.profile?.targetLow + input.profile?.targetHigh) / 2 || 110,
        max_iob: input.profile?.maxIob || 3,
        max_basal: input.profile?.maxBasal || 4,
        dia: input.profile?.dia || 5,
        max_daily_basal: input.profile?.maxDailyBasal || input.profile?.basalRate * 3 || 3,
        max_daily_safety_multiplier: 3,
        current_basal_safety_multiplier: 4,
        type: 'current'
    };
    
    // autosens_data
    const autosens_data = {
        ratio: input.autosensData?.ratio || 1.0
    };
    
    // meal_data
    const meal_data = {
        carbs: input.mealData?.carbs || 0,
        mealCOB: input.mealData?.cob || 0,
        slopeFromMaxDeviation: input.mealData?.slopeFromMaxDeviation || 0,
        slopeFromMinDeviation: input.mealData?.slopeFromMinDeviation || 0,
        lastCarbTime: input.mealData?.lastCarbTime || 0
    };
    
    const microBolusAllowed = input.microBolusAllowed || false;
    const reservoir_data = null;
    const currentTime = input.glucoseStatus.timestamp ? new Date(input.glucoseStatus.timestamp) : new Date();
    
    return {
        glucose_status,
        currenttemp,
        iob_data,
        profile,
        autosens_data,
        meal_data,
        tempBasalFunctions,
        microBolusAllowed,
        reservoir_data,
        currentTime
    };
}

/**
 * Validate output against expected values and assertions
 */
function validateOutput(output, vector) {
    const results = {
        passed: true,
        failures: [],
        warnings: []
    };
    
    const expected = vector.expected || {};
    const assertions = vector.assertions || [];
    
    // Check expected values
    if (expected.rate !== undefined) {
        if (typeof expected.rate === 'object') {
            // Range check
            if (output.rate < expected.rate.min || output.rate > expected.rate.max) {
                results.passed = false;
                results.failures.push(`rate ${output.rate} not in range [${expected.rate.min}, ${expected.rate.max}]`);
            }
        } else {
            // Exact match (with tolerance)
            if (Math.abs(output.rate - expected.rate) > 0.01) {
                results.passed = false;
                results.failures.push(`rate ${output.rate} != expected ${expected.rate}`);
            }
        }
    }
    
    if (expected.duration !== undefined && output.duration !== expected.duration) {
        results.passed = false;
        results.failures.push(`duration ${output.duration} != expected ${expected.duration}`);
    }
    
    if (expected.eventualBG !== undefined) {
        if (typeof expected.eventualBG === 'object') {
            if (output.eventualBG < expected.eventualBG.min || output.eventualBG > expected.eventualBG.max) {
                results.passed = false;
                results.failures.push(`eventualBG ${output.eventualBG} not in range [${expected.eventualBG.min}, ${expected.eventualBG.max}]`);
            }
        } else {
            if (Math.abs(output.eventualBG - expected.eventualBG) > 1) {
                results.passed = false;
                results.failures.push(`eventualBG ${output.eventualBG} != expected ${expected.eventualBG}`);
            }
        }
    }
    
    // Check semantic assertions
    for (const assertion of assertions) {
        switch (assertion.type) {
            case 'rate_increased':
                if (output.rate <= (assertion.baseline || 0)) {
                    results.passed = false;
                    results.failures.push(`rate_increased: ${output.rate} <= baseline ${assertion.baseline}`);
                }
                break;
                
            case 'rate_decreased':
                if (output.rate >= (assertion.baseline || 999)) {
                    results.passed = false;
                    results.failures.push(`rate_decreased: ${output.rate} >= baseline ${assertion.baseline}`);
                }
                break;
                
            case 'rate_zero':
                if (output.rate !== 0) {
                    results.passed = false;
                    results.failures.push(`rate_zero: rate is ${output.rate}`);
                }
                break;
                
            case 'no_smb':
                if (output.units && output.units > 0) {
                    results.passed = false;
                    results.failures.push(`no_smb: SMB of ${output.units} delivered`);
                }
                break;
                
            case 'smb_delivered':
                if (!output.units || output.units <= 0) {
                    results.warnings.push(`smb_delivered: no SMB in output`);
                }
                break;
                
            case 'safety_limit':
                const field = assertion.field || 'rate';
                const value = output[field];
                if (assertion.max !== undefined && value > assertion.max) {
                    results.passed = false;
                    results.failures.push(`safety_limit: ${field}=${value} > max ${assertion.max}`);
                }
                if (assertion.min !== undefined && value < assertion.min) {
                    results.passed = false;
                    results.failures.push(`safety_limit: ${field}=${value} < min ${assertion.min}`);
                }
                break;
        }
    }
    
    return results;
}

/**
 * Load all vectors from a directory
 */
function loadVectors(dir) {
    const vectors = [];
    const categories = fs.readdirSync(dir);
    
    for (const category of categories) {
        const categoryPath = path.join(dir, category);
        if (!fs.statSync(categoryPath).isDirectory()) continue;
        
        const files = fs.readdirSync(categoryPath).filter(f => f.endsWith('.json'));
        for (const file of files) {
            try {
                const content = fs.readFileSync(path.join(categoryPath, file), 'utf8');
                const vector = JSON.parse(content);
                vector._file = `${category}/${file}`;
                vectors.push(vector);
            } catch (e) {
                console.error(`Error loading ${category}/${file}:`, e.message);
            }
        }
    }
    
    return vectors;
}

/**
 * Run all conformance tests
 */
function runConformanceTests(vectorsDir, outputFile) {
    log('oref0 Conformance Test Runner');
    log('==============================');
    log(`Loading vectors from: ${vectorsDir}`);
    
    const vectors = loadVectors(vectorsDir);
    log(`Loaded ${vectors.length} test vectors\n`);
    
    const results = {
        runner: 'oref0',
        timestamp: new Date().toISOString(),
        vectorsDir,
        summary: {
            total: vectors.length,
            passed: 0,
            failed: 0,
            errors: 0
        },
        categories: {},
        details: []
    };
    
    for (const vector of vectors) {
        const category = vector.metadata?.category || 'unknown';
        if (!results.categories[category]) {
            results.categories[category] = { passed: 0, failed: 0, errors: 0 };
        }
        
        const detail = {
            id: vector.metadata?.id,
            name: vector.metadata?.name,
            category,
            file: vector._file
        };
        
        try {
            // Transform and execute
            suppressConsole();
            const oref0Input = vectorToOref0Input(vector);
            const output = determine_basal(
                oref0Input.glucose_status,
                oref0Input.currenttemp,
                oref0Input.iob_data,
                oref0Input.profile,
                oref0Input.autosens_data,
                oref0Input.meal_data,
                oref0Input.tempBasalFunctions,
                oref0Input.microBolusAllowed,
                oref0Input.reservoir_data,
                oref0Input.currentTime
            );
            restoreConsole();
            
            // Validate
            const validation = validateOutput(output, vector);
            
            detail.output = {
                rate: output.rate,
                duration: output.duration,
                eventualBG: output.eventualBG,
                reason: output.reason?.substring(0, 100)
            };
            detail.validation = validation;
            
            if (validation.passed) {
                results.summary.passed++;
                results.categories[category].passed++;
                detail.status = 'PASS';
            } else {
                results.summary.failed++;
                results.categories[category].failed++;
                detail.status = 'FAIL';
            }
            
        } catch (e) {
            results.summary.errors++;
            results.categories[category].errors++;
            detail.status = 'ERROR';
            detail.error = e.message;
        }
        
        results.details.push(detail);
        
        // Progress indicator
        const status = detail.status === 'PASS' ? '✓' : detail.status === 'FAIL' ? '✗' : '!';
        process.stdout.write(status);
    }
    
    log('\n');
    
    // Summary
    log('Results:');
    log(`  Passed: ${results.summary.passed}/${results.summary.total}`);
    log(`  Failed: ${results.summary.failed}`);
    log(`  Errors: ${results.summary.errors}`);
    log('\nBy category:');
    for (const [cat, stats] of Object.entries(results.categories)) {
        const total = stats.passed + stats.failed + stats.errors;
        log(`  ${cat}: ${stats.passed}/${total} passed`);
    }
    
    // Write results
    const outputDir = path.dirname(outputFile);
    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
    }
    fs.writeFileSync(outputFile, JSON.stringify(results, null, 2));
    log(`\nResults written to: ${outputFile}`);
    
    // Exit code
    return results.summary.failed === 0 && results.summary.errors === 0 ? 0 : 1;
}

// CLI
const args = process.argv.slice(2);
let vectorsDir = VECTORS_DIR;
let outputFile = DEFAULT_OUTPUT;

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--vectors' && args[i+1]) {
        vectorsDir = args[++i];
    } else if (args[i] === '--output' && args[i+1]) {
        outputFile = args[++i];
    } else if (args[i] === '--help') {
        log('Usage: node oref0-runner.js [--vectors DIR] [--output FILE] [--quiet]');
        process.exit(0);
    }
    // --quiet/-q already parsed at startup
}

const exitCode = runConformanceTests(vectorsDir, outputFile);
process.exit(exitCode);
