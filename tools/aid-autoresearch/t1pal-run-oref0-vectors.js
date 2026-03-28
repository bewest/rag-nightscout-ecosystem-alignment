#!/usr/bin/env node
/**
 * run-oref0-vectors.js
 * 
 * Execute ALG-XVAL test vectors against oref0 determine-basal.
 * Outputs comparison results for cross-validation.
 * 
 * Trace: ALG-XVAL-021
 * 
 * Usage:
 *   node scripts/run-oref0-vectors.js [--vector-file <name>] [--output-dir <path>]
 */

const fs = require('fs');
const path = require('path');

// Import oref0 determine-basal and tempBasalFunctions
const determineBasalPath = path.join(__dirname, '../externals/oref0/lib/determine-basal/determine-basal.js');
const tempBasalFunctionsPath = path.join(__dirname, '../externals/oref0/lib/basal-set-temp.js');
const determine_basal = require(determineBasalPath);
const tempBasalFunctions = require(tempBasalFunctionsPath);

// Configuration
const XVAL_DIR = path.join(__dirname, '../conformance/algorithm/xval');
const RESULTS_DIR = path.join(XVAL_DIR, 'results');

/**
 * Build oref0 glucose_status from vector input
 */
function buildGlucoseStatus(input) {
    return {
        glucose: input.glucose || 100,
        delta: input.delta || 0,
        short_avgdelta: input.delta || 0,
        long_avgdelta: input.delta || 0,
        date: Date.now()
    };
}

/**
 * Build oref0 profile from vector input
 */
function buildProfile(input) {
    return {
        max_iob: input.maxIOB || 3.5,
        max_daily_basal: input.maxBasal || 3.5,
        max_basal: input.maxBasal || 3.5,
        max_bg: input.targetHigh || 120,
        min_bg: input.targetLow || 100,
        target_bg: ((input.targetLow || 100) + (input.targetHigh || 120)) / 2,
        sens: input.isf || 50,
        carb_ratio: input.icr || 10,
        current_basal: input.scheduledBasal || input.currentBasal || 1.0,
        dia: 6,
        // SMB settings
        enableSMB_with_COB: input.enableSMB_with_COB || false,
        enableSMB_with_temptarget: false,
        allowSMB_with_high_temptarget_and_target: false,
        enableUAM: input.enableUAM || false,
        SMBInterval: 3,
        bolus_increment: 0.1,
        maxSMBBasalMinutes: 30,
        maxUAMSMBBasalMinutes: 30,
        // Safety
        skip_neutral_temps: true,
        remainingCarbsCap: 90,
        remainingCarbsFraction: 1.0,
        A52_risk_enable: false,
        // Autosens
        autosens_max: 1.2,
        autosens_min: 0.8,
        out_units: 'mg/dL'
    };
}

/**
 * Build oref0 iob_data from vector input
 */
function buildIOBData(input) {
    return {
        iob: input.iob || 0,
        basaliob: input.iob || 0,
        bolussnooze: 0,
        activity: 0,
        lastBolusTime: 0,
        time: new Date().toISOString()
    };
}

/**
 * Build oref0 meal_data from vector input
 */
function buildMealData(input) {
    return {
        carbs: 0,
        mealCOB: input.cob || 0,
        slopeFromMaxDeviation: 0,
        slopeFromMinDeviation: 0,
        lastCarbTime: 0
    };
}

/**
 * Build oref0 currenttemp from vector input
 */
function buildCurrentTemp(input) {
    if (input.currentTemp) {
        return {
            rate: input.currentTemp.rate,
            duration: input.currentTemp.remaining_minutes || input.currentTemp.duration || 0
        };
    }
    return { rate: 0, duration: 0 };
}

/**
 * Build autosens_data (typically 1.0 for tests)
 */
function buildAutosens() {
    return {
        ratio: 1.0,
        rawRatio: 1.0
    };
}

/**
 * Run a single test case through oref0
 */
function runTestCase(testCase) {
    const input = testCase.input;
    
    try {
        const glucose_status = buildGlucoseStatus(input);
        const currenttemp = buildCurrentTemp(input);
        const iob_data = buildIOBData(input);
        const profile = buildProfile(input);
        const autosens = buildAutosens();
        const meal_data = buildMealData(input);
        
        // Run determine-basal with tempBasalFunctions
        const result = determine_basal(
            glucose_status,
            currenttemp,
            iob_data,
            profile,
            autosens,
            meal_data,
            tempBasalFunctions
        );
        
        return {
            id: testCase.id,
            scenario: testCase.scenario,
            success: true,
            oref0_output: {
                rate: result.rate,
                duration: result.duration,
                reason: result.reason,
                temp: result.temp,
                deliverAt: result.deliverAt,
                units: result.units,
                error: result.error
            },
            expected: testCase.expected
        };
    } catch (error) {
        return {
            id: testCase.id,
            scenario: testCase.scenario,
            success: false,
            error: error.message,
            expected: testCase.expected
        };
    }
}

/**
 * Compare oref0 output with expected values
 */
function compareResults(result) {
    if (!result.success) {
        return { match: false, reason: `Error: ${result.error}` };
    }
    
    const output = result.oref0_output;
    const expected = result.expected;
    const issues = [];
    
    // Check rate
    if (expected.rate !== undefined) {
        if (Math.abs((output.rate || 0) - expected.rate) > 0.05) {
            issues.push(`rate: expected ${expected.rate}, got ${output.rate}`);
        }
    }
    
    // Check rate bounds
    if (expected.rate_min !== undefined && (output.rate || 0) < expected.rate_min) {
        issues.push(`rate too low: expected >= ${expected.rate_min}, got ${output.rate}`);
    }
    if (expected.rate_max !== undefined && (output.rate || 0) > expected.rate_max) {
        issues.push(`rate too high: expected <= ${expected.rate_max}, got ${output.rate}`);
    }
    
    // Check duration
    if (expected.duration !== undefined) {
        if ((output.duration || 0) !== expected.duration) {
            issues.push(`duration: expected ${expected.duration}, got ${output.duration}`);
        }
    }
    
    // Check action (map to temp type)
    if (expected.action !== undefined) {
        const tempAction = output.temp || (output.rate === 0 ? 'suspend' : 'set_temp');
        if (expected.action === 'suspend' && output.rate !== 0) {
            issues.push(`action: expected suspend, got rate ${output.rate}`);
        }
    }
    
    return {
        match: issues.length === 0,
        issues: issues,
        reason: output.reason
    };
}

/**
 * Process a vector file
 */
function processVectorFile(filename) {
    const filePath = path.join(XVAL_DIR, `${filename}.json`);
    
    if (!fs.existsSync(filePath)) {
        console.error(`Vector file not found: ${filePath}`);
        return null;
    }
    
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    const results = {
        source: filename,
        version: data.version,
        track: data.track,
        timestamp: new Date().toISOString(),
        summary: { total: 0, passed: 0, failed: 0, errors: 0 },
        testResults: []
    };
    
    for (const testCase of data.testCases) {
        const result = runTestCase(testCase);
        const comparison = compareResults(result);
        
        results.testResults.push({
            ...result,
            comparison: comparison
        });
        
        results.summary.total++;
        if (!result.success) {
            results.summary.errors++;
        } else if (comparison.match) {
            results.summary.passed++;
        } else {
            results.summary.failed++;
        }
    }
    
    return results;
}

/**
 * Main execution
 */
function main() {
    // Ensure results directory exists
    if (!fs.existsSync(RESULTS_DIR)) {
        fs.mkdirSync(RESULTS_DIR, { recursive: true });
    }
    
    const vectorFiles = [
        'oref0-extracted-vectors',
        'boundary-vectors',
        'temp-basal-vectors',
        'smb-decision-vectors'
    ];
    
    console.log('=== oref0 Cross-Validation Runner ===');
    console.log(`Trace: ALG-XVAL-021`);
    console.log(`Timestamp: ${new Date().toISOString()}\n`);
    
    const allResults = {
        timestamp: new Date().toISOString(),
        files: []
    };
    
    for (const file of vectorFiles) {
        console.log(`Processing ${file}...`);
        const results = processVectorFile(file);
        
        if (results) {
            allResults.files.push(results);
            
            console.log(`  Total: ${results.summary.total}`);
            console.log(`  Passed: ${results.summary.passed}`);
            console.log(`  Failed: ${results.summary.failed}`);
            console.log(`  Errors: ${results.summary.errors}`);
            
            // Show failures
            for (const tr of results.testResults) {
                if (!tr.success) {
                    console.log(`  ❌ ${tr.id}: ${tr.error}`);
                } else if (!tr.comparison.match) {
                    console.log(`  ⚠️ ${tr.id}: ${tr.comparison.issues.join(', ')}`);
                }
            }
            console.log('');
        }
    }
    
    // Write results
    const outputPath = path.join(RESULTS_DIR, 'oref0-results.json');
    fs.writeFileSync(outputPath, JSON.stringify(allResults, null, 2));
    console.log(`Results written to: ${outputPath}`);
    
    // Summary
    const totalPassed = allResults.files.reduce((sum, f) => sum + f.summary.passed, 0);
    const totalFailed = allResults.files.reduce((sum, f) => sum + f.summary.failed, 0);
    const totalErrors = allResults.files.reduce((sum, f) => sum + f.summary.errors, 0);
    const total = allResults.files.reduce((sum, f) => sum + f.summary.total, 0);
    
    console.log(`\n=== Summary ===`);
    console.log(`Total: ${total} | Passed: ${totalPassed} | Failed: ${totalFailed} | Errors: ${totalErrors}`);
    
    // Exit code
    process.exit(totalFailed + totalErrors > 0 ? 1 : 0);
}

main();
