// SPDX-License-Identifier: AGPL-3.0-or-later
//
// T1PalAdapterCLI — JSON-over-stdio adapter for the Nightscout ecosystem test harness.
//
// Protocol:
//   stdin  → { "mode": "execute"|"validate-input"|"describe", "input": {...}, "verbose": false, "algorithm": "oref0" }
//   stdout ← adapter-output.schema.json conformant JSON
//
// This bridges the JS test-harness adapter protocol to the T1PalAlgorithm Swift library,
// giving the harness access to all registered algorithms (oref0, Loop, Loop-Tidepool, GlucOS, etc.).

import Foundation
import T1PalAlgorithm
import T1PalCore

// MARK: - Wire Types (Codable structs matching adapter JSON schemas)

/// Top-level request read from stdin
struct AdapterRequest: Codable {
    let mode: String
    let input: AdapterInput?
    let verbose: Bool?
    let algorithm: String?
}

/// Matches adapter-input.schema.json
struct AdapterInput: Codable {
    let clock: String
    let glucoseStatus: GlucoseStatus
    let iob: IOBStatus
    let profile: ProfileInput
    let mealData: MealData?
    let currentTemp: CurrentTemp?
    let autosensData: AutosensData?
    let microBolusAllowed: Bool?
    let flatBGsDetected: Bool?
    let glucoseHistory: [GlucoseHistoryEntry]?
    let doseHistory: [DoseHistoryEntry]?
    let carbHistory: [CarbHistoryEntry]?
    let effectModifiers: [EffectModifierInput]?
}

struct GlucoseStatus: Codable {
    let glucose: Double
    let delta: Double?
    let shortAvgDelta: Double?
    let longAvgDelta: Double?
    let timestamp: String?
    let noise: Double?
    let glucoseUnit: String?
}

struct IOBStatus: Codable {
    let iob: Double
    let basalIob: Double?
    let bolusIob: Double?
    let activity: Double?
    let iobWithZeroTemp: IOBWithZeroTemp?
}

struct IOBWithZeroTemp: Codable {
    let iob: Double?
    let basaliob: Double?
    let bolussnooze: Double?
    let activity: Double?
    let lastBolusTime: Double?
    let time: String?
}

struct ProfileInput: Codable {
    let basalRate: Double
    let sensitivity: Double
    let carbRatio: Double
    let targetLow: Double
    let targetHigh: Double
    let maxIob: Double?
    let maxBasal: Double?
    let dia: Double?
    let maxDailyBasal: Double?
    let units: String?
    let enableSMB: Bool?
    let enableUAM: Bool?
    let maxSMBBasalMinutes: Double?
    let maxUAMSMBBasalMinutes: Double?
    let smbInterval: Double?
}

struct MealData: Codable {
    let carbs: Double?
    let cob: Double?
    let lastCarbTime: Double?
    let slopeFromMaxDeviation: Double?
    let slopeFromMinDeviation: Double?
}

struct CurrentTemp: Codable {
    let rate: Double?
    let duration: Double?
}

struct AutosensData: Codable {
    let ratio: Double?
}

struct GlucoseHistoryEntry: Codable {
    let glucose: Double
    let timestamp: String
}

struct DoseHistoryEntry: Codable {
    let type: String?
    let units: Double?
    let rate: Double?
    let startTime: String
    let duration: Double?
}

struct CarbHistoryEntry: Codable {
    let carbs: Double
    let timestamp: String
    let absorptionTime: Double?
}

struct EffectModifierInput: Codable {
    let source: String?
    let isfMultiplier: Double?
    let crMultiplier: Double?
    let basalMultiplier: Double?
    let confidence: Double?
    let reason: String?
    let validUntil: String?
}

// MARK: - Output Types

struct AdapterOutput: Codable {
    let algorithm: AlgorithmInfo
    let decision: DecisionOutput
    let predictions: PredictionsOutput?
    let state: StateOutput
    let metadata: MetadataOutput?
}

struct AlgorithmInfo: Codable {
    let name: String
    let version: String
}

struct DecisionOutput: Codable {
    let rate: Double?
    let duration: Double?
    let smb: Double?
    let reason: String
}

struct PredictionsOutput: Codable {
    let eventualBG: Double?
    let minPredBG: Double?
    let iob: [Double]?
    let zt: [Double]?
    let cob: [Double]?
    let uam: [Double]?
}

struct StateOutput: Codable {
    let iob: Double
    let cob: Double
    let bg: Double
    let tick: String
    let insulinReq: Double?
    let sensitivityRatio: Double
}

struct MetadataOutput: Codable {
    let executionTimeMs: Double?
    let warnings: [String]?
    let nativeInput: AnyCodable?
    let nativeOutput: AnyCodable?
}

/// Type-erased Codable wrapper for arbitrary JSON
struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) {
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let dict = try? container.decode([String: AnyCodable].self) {
            value = dict.mapValues { $0.value }
        } else if let arr = try? container.decode([AnyCodable].self) {
            value = arr.map { $0.value }
        } else if let str = try? container.decode(String.self) {
            value = str
        } else if let num = try? container.decode(Double.self) {
            value = num
        } else if let bool = try? container.decode(Bool.self) {
            value = bool
        } else {
            value = NSNull()
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { AnyCodable($0) })
        case let arr as [Any]:
            try container.encode(arr.map { AnyCodable($0) })
        case let str as String:
            try container.encode(str)
        case let num as Double:
            try container.encode(num)
        case let num as Int:
            try container.encode(num)
        case let bool as Bool:
            try container.encode(bool)
        default:
            try container.encodeNil()
        }
    }
}

// MARK: - Error Response

struct ErrorResponse: Codable {
    let error: String
    let name: String?
    let algorithm: String?
    let status: String?
}

// MARK: - Translation Layer

let iso8601: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return f
}()

let iso8601NoFrac: ISO8601DateFormatter = {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    return f
}()

func parseDate(_ str: String) -> Date {
    iso8601.date(from: str)
        ?? iso8601NoFrac.date(from: str)
        ?? Date()
}

func trendFromDelta(_ delta: Double?) -> GlucoseTrend {
    guard let d = delta else { return .flat }
    // Convert 5-min delta to mg/dL per minute
    let rate = d / 5.0
    return GlucoseTrend.fromRate(rate)
}

func tickString(from delta: Double?) -> String {
    guard let d = delta else { return "flat" }
    if d > 5 { return "++" }
    if d > 0 { return "+" }
    if d < -5 { return "--" }
    if d < 0 { return "-" }
    return "flat"
}

/// Translate adapter-input JSON → AlgorithmInputs
func translateInput(_ input: AdapterInput) -> (AlgorithmInputs, [String]) {
    var warnings: [String] = []
    let clock = parseDate(input.clock)

    // Build glucose array — use glucoseHistory if available, otherwise single point
    var glucoseReadings: [GlucoseReading] = []
    if let history = input.glucoseHistory, !history.isEmpty {
        glucoseReadings = history.map { entry in
            GlucoseReading(
                glucose: entry.glucose,
                timestamp: parseDate(entry.timestamp),
                trend: .flat,
                source: "harness"
            )
        }
        // Sort newest first (AlgorithmInputs convention)
        glucoseReadings.sort { $0.timestamp > $1.timestamp }
    } else {
        // Synthesize minimal glucose history from single point + delta.
        // The oref0-endtoend vectors only provide glucoseStatus (a snapshot);
        // algorithms need >= 3 readings.  We extrapolate backwards using delta.
        let ts = input.glucoseStatus.timestamp.map { parseDate($0) } ?? clock
        let delta = input.glucoseStatus.delta ?? 0
        let trend = trendFromDelta(input.glucoseStatus.delta)
        let current = input.glucoseStatus.glucose

        // Generate 6 synthetic points at 5-min intervals going backwards
        for i in 0..<6 {
            let t = ts.addingTimeInterval(Double(-i) * 300)
            let bg = current - delta * Double(i)
            glucoseReadings.append(GlucoseReading(
                glucose: bg,
                timestamp: t,
                trend: trend,
                source: "harness-synthetic"
            ))
        }
        warnings.append("Synthesized \(glucoseReadings.count) glucose points from glucoseStatus + delta")
    }

    // Build TherapyProfile
    let profile = TherapyProfile(
        basalRates: [BasalRate(startTime: 0, rate: input.profile.basalRate)],
        carbRatios: [CarbRatio(startTime: 0, ratio: input.profile.carbRatio)],
        sensitivityFactors: [SensitivityFactor(startTime: 0, factor: input.profile.sensitivity)],
        targetGlucose: TargetRange(low: input.profile.targetLow, high: input.profile.targetHigh),
        maxIOB: input.profile.maxIob ?? 10.0,
        maxBolus: 5.0,
        maxBasalRate: input.profile.maxBasal,
        insulinModel: nil
    )

    // Build dose history if available
    let doses: [InsulinDose]? = input.doseHistory?.compactMap { entry in
        let units = entry.units ?? (entry.rate ?? 0) * (entry.duration ?? 30) / 60.0
        guard units > 0 else { return nil }
        return InsulinDose(
            units: units,
            timestamp: parseDate(entry.startTime),
            type: .novolog,
            source: "harness"
        )
    }

    // Build carb history if available
    let carbs: [CarbEntry]? = input.carbHistory?.map { entry in
        let absorptionType: CarbAbsorptionType
        if let t = entry.absorptionTime {
            if t <= 120 { absorptionType = .fast }
            else if t <= 240 { absorptionType = .medium }
            else { absorptionType = .slow }
        } else {
            absorptionType = .medium
        }
        return CarbEntry(
            grams: entry.carbs,
            timestamp: parseDate(entry.timestamp),
            absorptionType: absorptionType,
            source: "harness"
        )
    }

    // Build effect modifiers if available
    let modifiers: [EffectModifier]? = input.effectModifiers?.map { m in
        EffectModifier(
            isfMultiplier: m.isfMultiplier ?? 1.0,
            crMultiplier: m.crMultiplier ?? 1.0,
            basalMultiplier: m.basalMultiplier ?? 1.0,
            source: m.source ?? "harness",
            confidence: m.confidence ?? 1.0,
            validUntil: m.validUntil.map { parseDate($0) },
            reason: m.reason
        )
    }

    let inputs = AlgorithmInputs(
        glucose: glucoseReadings,
        insulinOnBoard: input.iob.iob,
        carbsOnBoard: input.mealData?.cob ?? 0,
        profile: profile,
        currentTime: clock,
        doseHistory: doses,
        carbHistory: carbs,
        effectModifiers: modifiers
    )

    return (inputs, warnings)
}

/// Translate AlgorithmDecision → adapter-output JSON
func translateOutput(
    decision: AlgorithmDecision,
    engine: any AlgorithmEngine,
    input: AdapterInput,
    warnings: [String],
    executionMs: Double,
    verbose: Bool
) -> AdapterOutput {
    let preds: PredictionsOutput?
    if let p = decision.predictions {
        let allPreds = p.iob + p.cob + p.uam + p.zt
        let eventualBG = p.iob.last
        let minPredBG = allPreds.isEmpty ? nil : allPreds.min()
        preds = PredictionsOutput(
            eventualBG: eventualBG,
            minPredBG: minPredBG,
            iob: p.iob.isEmpty ? nil : p.iob,
            zt: p.zt.isEmpty ? nil : p.zt,
            cob: p.cob.isEmpty ? nil : p.cob,
            uam: p.uam.isEmpty ? nil : p.uam
        )
    } else {
        preds = nil
    }

    // Compute insulinReq: (eventualBG - target) / sensitivity
    // For algorithms that embed these in the reason string (like oref0),
    // parse them out. Otherwise compute from predictions.
    let sensitivity = input.profile.sensitivity
    let target = (input.profile.targetLow + input.profile.targetHigh) / 2.0
    var computedEventualBG: Double? = preds?.eventualBG
    var computedInsulinReq: Double? = nil

    // Parse "eventualBG NNN" and "insulinReq N.NN" from reason string
    let reason = decision.reason
    if computedEventualBG == nil {
        if let range = reason.range(of: #"eventualBG\s+([\d.]+)"#, options: .regularExpression) {
            let match = reason[range]
            let numStr = match.split(separator: " ").last ?? ""
            computedEventualBG = Double(numStr)
        }
    }
    if let range = reason.range(of: #"insulinReq\s+([\d.-]+)"#, options: .regularExpression) {
        let match = reason[range]
        let numStr = match.split(separator: " ").last ?? ""
        computedInsulinReq = Double(numStr)
    }

    // Fallback: compute insulinReq from eventualBG
    if computedInsulinReq == nil, let ebg = computedEventualBG, sensitivity > 0, ebg > target {
        computedInsulinReq = (ebg - target) / sensitivity
    }

    // Build predictions with parsed eventualBG
    let finalPreds: PredictionsOutput?
    if preds != nil {
        finalPreds = preds
    } else if let ebg = computedEventualBG {
        finalPreds = PredictionsOutput(
            eventualBG: ebg,
            minPredBG: nil,
            iob: nil, zt: nil, cob: nil, uam: nil
        )
    } else {
        finalPreds = nil
    }

    let state = StateOutput(
        iob: input.iob.iob,
        cob: input.mealData?.cob ?? 0,
        bg: input.glucoseStatus.glucose,
        tick: tickString(from: input.glucoseStatus.delta),
        insulinReq: computedInsulinReq,
        sensitivityRatio: input.autosensData?.ratio ?? 1.0
    )

    return AdapterOutput(
        algorithm: AlgorithmInfo(name: engine.name, version: engine.version),
        decision: DecisionOutput(
            rate: decision.suggestedTempBasal?.rate,
            duration: decision.suggestedTempBasal.map { $0.duration / 60.0 },
            smb: decision.suggestedBolus,
            reason: decision.reason
        ),
        predictions: finalPreds,
        state: state,
        metadata: MetadataOutput(
            executionTimeMs: executionMs,
            warnings: warnings.isEmpty ? nil : warnings,
            nativeInput: nil,
            nativeOutput: nil
        )
    )
}

// MARK: - Mode Handlers

func handleDescribe(algorithmName: String?) -> Data {
    let registry = AlgorithmRegistry.shared
    let infos = registry.detailedInfo

    struct DescribeResponse: Codable {
        let name: String
        let version: String
        let algorithms: [AlgInfo]

        struct AlgInfo: Codable {
            let name: String
            let version: String
            let origin: String
            let predictions: Bool
            let smb: Bool
            let uam: Bool
            let dynamicISF: Bool
            let autosens: Bool
            let minGlucoseHistory: Int
        }
    }

    let resp = DescribeResponse(
        name: "t1pal-swift",
        version: "1.0.0",
        algorithms: infos.map { info in
            DescribeResponse.AlgInfo(
                name: info.name,
                version: info.version,
                origin: info.origin.rawValue,
                predictions: info.capabilities.providesPredictions,
                smb: info.capabilities.supportsSMB,
                uam: info.capabilities.supportsUAM,
                dynamicISF: info.capabilities.supportsDynamicISF,
                autosens: info.capabilities.supportsAutosens,
                minGlucoseHistory: info.capabilities.minGlucoseHistory
            )
        }
    )

    return try! JSONEncoder.harness.encode(resp)
}

func handleValidateInput(input: AdapterInput, algorithmName: String?) -> Data {
    let (nativeInput, warnings) = translateInput(input)

    struct ValidateResponse: Codable {
        let nativeInput: NativeInputSummary
        let fieldMapping: [FieldMap]
        let warnings: [String]

        struct NativeInputSummary: Codable {
            let glucoseCount: Int
            let latestGlucose: Double
            let iob: Double
            let cob: Double
            let basalRate: Double
            let sensitivity: Double
            let carbRatio: Double
            let targetLow: Double
            let targetHigh: Double
            let maxIOB: Double
            let hasDoseHistory: Bool
            let hasCarbHistory: Bool
            let hasEffectModifiers: Bool
        }

        struct FieldMap: Codable {
            let adapterField: String
            let nativeField: String
            let value: String
        }
    }

    let latest = nativeInput.glucose.first
    let resp = ValidateResponse(
        nativeInput: ValidateResponse.NativeInputSummary(
            glucoseCount: nativeInput.glucose.count,
            latestGlucose: latest?.glucose ?? 0,
            iob: nativeInput.insulinOnBoard,
            cob: nativeInput.carbsOnBoard,
            basalRate: nativeInput.profile.basalRates.first?.rate ?? 0,
            sensitivity: nativeInput.profile.sensitivityFactors.first?.factor ?? 0,
            carbRatio: nativeInput.profile.carbRatios.first?.ratio ?? 0,
            targetLow: nativeInput.profile.targetGlucose.low,
            targetHigh: nativeInput.profile.targetGlucose.high,
            maxIOB: nativeInput.profile.maxIOB,
            hasDoseHistory: nativeInput.doseHistory != nil,
            hasCarbHistory: nativeInput.carbHistory != nil,
            hasEffectModifiers: nativeInput.effectModifiers != nil
        ),
        fieldMapping: [
            .init(adapterField: "glucoseStatus.glucose", nativeField: "glucose[0].glucose", value: "\(latest?.glucose ?? 0)"),
            .init(adapterField: "iob.iob", nativeField: "insulinOnBoard", value: "\(nativeInput.insulinOnBoard)"),
            .init(adapterField: "mealData.cob", nativeField: "carbsOnBoard", value: "\(nativeInput.carbsOnBoard)"),
            .init(adapterField: "profile.basalRate", nativeField: "profile.basalRates[0].rate", value: "\(nativeInput.profile.basalRates.first?.rate ?? 0)"),
            .init(adapterField: "profile.sensitivity", nativeField: "profile.sensitivityFactors[0].factor", value: "\(nativeInput.profile.sensitivityFactors.first?.factor ?? 0)"),
            .init(adapterField: "profile.carbRatio", nativeField: "profile.carbRatios[0].ratio", value: "\(nativeInput.profile.carbRatios.first?.ratio ?? 0)"),
        ],
        warnings: warnings
    )

    return try! JSONEncoder.harness.encode(resp)
}

func handleExecute(input: AdapterInput, algorithmName: String?, verbose: Bool) -> Data {
    let registry = AlgorithmRegistry.shared

    // Resolve which algorithm to run
    let engine: any AlgorithmEngine
    if let name = algorithmName, let alg = registry.algorithm(named: name) {
        engine = alg
    } else if let active = registry.activeAlgorithm {
        engine = active
    } else {
        let err = ErrorResponse(error: "No algorithm available", name: nil, algorithm: algorithmName, status: "error")
        return try! JSONEncoder.harness.encode(err)
    }

    let (nativeInput, warnings) = translateInput(input)

    // Validate
    let validationErrors = engine.validate(nativeInput)
    var allWarnings = warnings
    for ve in validationErrors {
        allWarnings.append(ve.localizedDescription)
    }

    // Execute with timing
    let start = DispatchTime.now()
    let decision: AlgorithmDecision
    do {
        decision = try engine.calculate(nativeInput)
    } catch {
        let err = ErrorResponse(
            error: "Algorithm execution failed: \(error.localizedDescription)",
            name: engine.name,
            algorithm: engine.name,
            status: "error"
        )
        return try! JSONEncoder.harness.encode(err)
    }
    let end = DispatchTime.now()
    let elapsedMs = Double(end.uptimeNanoseconds - start.uptimeNanoseconds) / 1_000_000.0

    let output = translateOutput(
        decision: decision,
        engine: engine,
        input: input,
        warnings: allWarnings,
        executionMs: elapsedMs,
        verbose: verbose
    )

    return try! JSONEncoder.harness.encode(output)
}

// MARK: - JSON Encoder Configuration

extension JSONEncoder {
    static let harness: JSONEncoder = {
        let enc = JSONEncoder()
        enc.outputFormatting = [.sortedKeys]
        return enc
    }()
}

// MARK: - Main

func main() {
    // Read all of stdin
    let data = FileHandle.standardInput.readDataToEndOfFile()

    guard !data.isEmpty else {
        let err = ErrorResponse(error: "Empty stdin — expected JSON request", name: "t1pal-swift", algorithm: nil, status: "error")
        let json = try! JSONEncoder.harness.encode(err)
        FileHandle.standardOutput.write(json)
        FileHandle.standardOutput.write("\n".data(using: .utf8)!)
        return
    }

    // Parse request
    let request: AdapterRequest
    do {
        request = try JSONDecoder().decode(AdapterRequest.self, from: data)
    } catch {
        let err = ErrorResponse(error: "Invalid JSON: \(error.localizedDescription)", name: "t1pal-swift", algorithm: nil, status: "error")
        let json = try! JSONEncoder.harness.encode(err)
        FileHandle.standardOutput.write(json)
        FileHandle.standardOutput.write("\n".data(using: .utf8)!)
        return
    }

    // Dispatch by mode
    let result: Data
    switch request.mode {
    case "describe":
        result = handleDescribe(algorithmName: request.algorithm)

    case "validate-input":
        guard let input = request.input else {
            let err = ErrorResponse(error: "validate-input requires 'input' field", name: "t1pal-swift", algorithm: nil, status: "error")
            result = try! JSONEncoder.harness.encode(err)
            break
        }
        result = handleValidateInput(input: input, algorithmName: request.algorithm)

    case "execute":
        guard let input = request.input else {
            let err = ErrorResponse(error: "execute requires 'input' field", name: "t1pal-swift", algorithm: nil, status: "error")
            result = try! JSONEncoder.harness.encode(err)
            break
        }
        result = handleExecute(input: input, algorithmName: request.algorithm, verbose: request.verbose ?? false)

    default:
        let err = ErrorResponse(error: "Unknown mode: \(request.mode). Supported: execute, validate-input, describe", name: "t1pal-swift", algorithm: nil, status: "error")
        result = try! JSONEncoder.harness.encode(err)
    }

    FileHandle.standardOutput.write(result)
    FileHandle.standardOutput.write("\n".data(using: .utf8)!)
}

main()
