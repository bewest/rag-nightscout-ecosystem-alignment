/**
 * AAPS Kotlin adapter for cross-validation harness.
 *
 * Runs AAPS's actual Kotlin DetermineBasalSMB algorithm through the
 * JSON-over-stdio adapter protocol. This validates the real Kotlin code
 * path, not a JS approximation.
 *
 * Key differences from aaps-js adapter:
 *   - Executes the actual Kotlin DetermineBasalSMB class
 *   - Uses AAPS's native data classes (OapsProfile, IobTotal, etc.)
 *   - round_basal is identity (same as AAPS)
 *   - flatBGsDetected passed as parameter
 *   - aCOB prediction curve included
 */
package adapter

import adapter.aaps.*
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.*
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.roundToInt

private val json = Json {
    ignoreUnknownKeys = true
    isLenient = true
    encodeDefaults = true
    prettyPrint = false
}

// ── Wire Types (adapter protocol) ──────────────────────────────────

@Serializable
data class AdapterRequest(
    val mode: String = "execute",
    val verbose: Boolean = false,
    val input: JsonObject? = null,
    val algorithm: String? = null
)

@Serializable
data class AdapterOutput(
    val algorithm: AlgorithmInfo,
    val decision: Decision,
    val predictions: PredictionOutput,
    val state: StateOutput,
    val metadata: MetadataOutput
)

@Serializable
data class AlgorithmInfo(val name: String, val version: String)
@Serializable
data class Decision(val rate: Double?, val duration: Int?, val smb: Double?, val reason: String)

@Serializable
data class PredictionOutput(
    val eventualBG: Double?,
    val minPredBG: Double? = null,
    val iob: List<Int>? = null,
    val zt: List<Int>? = null,
    val cob: List<Int>? = null,
    val uam: List<Int>? = null,
    val acob: List<Int>? = null
)

@Serializable
data class StateOutput(
    val iob: Double, val cob: Double, val bg: Double,
    val tick: String, val insulinReq: Double?,
    val sensitivityRatio: Double
)

@Serializable
data class MetadataOutput(
    val executionTimeMs: Long,
    val warnings: List<String> = emptyList(),
    val nativeInput: JsonElement? = null,
    val nativeOutput: JsonElement? = null
)

@Serializable
data class ErrorOutput(val error: String, val algorithm: AlgorithmInfo, val stack: String? = null)

// ── IOB Array Generation ───────────────────────────────────────────

fun round(value: Double, digits: Int): Double {
    if (value.isNaN()) return Double.NaN
    val scale = Math.pow(10.0, digits.toDouble())
    return Math.round(value * scale) / scale
}

fun generateIobArray(iobSnapshot: JsonObject, dia: Double, currentTemp: JsonObject?): Array<IobTotal> {
    val diaMinutes = (if (dia > 0) dia else 5.0) * 60
    val ticks = 48
    val tau = diaMinutes / 1.85

    val iob0 = iobSnapshot["iob"]?.jsonPrimitive?.doubleOrNull ?: 0.0
    val basalIob0 = iobSnapshot["basalIob"]?.jsonPrimitive?.doubleOrNull ?: 0.0
    var activity0 = iobSnapshot["activity"]?.jsonPrimitive?.doubleOrNull ?: 0.0

    // IOB/tau activity derivation when activity is zero/missing but IOB > 0
    if (activity0 == 0.0 && iob0 != 0.0) {
        activity0 = iob0 / tau
    }

    val iobZT = iobSnapshot["iobWithZeroTemp"]?.let { if (it is JsonObject) it else null }
    var ztIob0 = iobZT?.get("iob")?.jsonPrimitive?.doubleOrNull ?: iob0
    var ztActivity0 = iobZT?.get("activity")?.jsonPrimitive?.doubleOrNull ?: activity0
    if (ztActivity0 == 0.0 && ztIob0 != 0.0) {
        ztActivity0 = ztIob0 / tau
    }

    val tempRate = currentTemp?.get("rate")?.jsonPrimitive?.doubleOrNull ?: 0.0
    val tempDuration = currentTemp?.get("duration")?.jsonPrimitive?.intOrNull ?: 0

    return Array(ticks) { i ->
        val t = i * 5.0
        val decay = exp(-t / tau)

        val tickIob = round(iob0 * decay, 3)
        val tickBasalIob = round(basalIob0 * decay, 3)
        val tickActivity = round(activity0 * decay, 5)

        var ztIob = ztIob0 * decay
        val ztActivity = round(ztActivity0 * decay, 5)

        if (tempRate > 0 && tempDuration > 0) {
            val remainMin = max(0.0, tempDuration - t)
            if (remainMin > 0) {
                val basalContrib = (tempRate / 60) * Math.min(5.0, remainMin)
                ztIob -= basalContrib * decay * 0.5
            }
        }

        IobTotal(
            time = (t * 60 * 1000).toLong(),
            iob = tickIob,
            activity = tickActivity,
            basaliob = tickBasalIob,
            iobWithZeroTemp = IobTotal(
                time = (t * 60 * 1000).toLong(),
                iob = round(ztIob, 3),
                activity = ztActivity
            )
        )
    }
}

// ── Input Translation ──────────────────────────────────────────────

fun translateInput(input: JsonObject): TranslatedInput {
    fun JsonObject.obj(key: String): JsonObject =
        this[key]?.let { if (it is JsonObject) it else null } ?: JsonObject(emptyMap())

    val gs = input.obj("glucoseStatus")
    val iob = input.obj("iob")
    val prof = input.obj("profile")
    val meal = input.obj("mealData")
    val temp = input.obj("currentTemp")
    val autosens = input.obj("autosensData")

    val basalRate = prof["basalRate"]?.jsonPrimitive?.doubleOrNull ?: 1.0
    val dia = prof["dia"]?.jsonPrimitive?.doubleOrNull ?: 5.0

    val gsTimestamp = gs["timestamp"]?.jsonPrimitive?.let {
        it.longOrNull ?: try { java.time.Instant.parse(it.content).toEpochMilli() } catch (_: Exception) { null }
    } ?: System.currentTimeMillis()

    val glucoseStatus = GlucoseStatusSMB(
        glucose = gs["glucose"]?.jsonPrimitive?.doubleOrNull ?: 100.0,
        delta = gs["delta"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
        shortAvgDelta = gs["shortAvgDelta"]?.jsonPrimitive?.doubleOrNull
            ?: gs["delta"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
        longAvgDelta = gs["longAvgDelta"]?.jsonPrimitive?.doubleOrNull
            ?: gs["delta"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
        date = gsTimestamp,
        noise = gs["noise"]?.jsonPrimitive?.doubleOrNull ?: 0.0
    )

    val currentTemp = CurrentTemp(
        rate = temp["rate"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
        duration = temp["duration"]?.jsonPrimitive?.intOrNull ?: 0,
        minutesrunning = null
    )

    val iobData = generateIobArray(iob, dia, temp)

    val profile = OapsProfile(
        dia = dia,
        min_5m_carbimpact = prof["min5mCarbImpact"]?.jsonPrimitive?.doubleOrNull ?: 8.0,
        max_iob = prof["maxIob"]?.jsonPrimitive?.doubleOrNull ?: 5.0,
        max_daily_basal = prof["maxDailyBasal"]?.jsonPrimitive?.doubleOrNull ?: basalRate,
        max_basal = prof["maxBasal"]?.jsonPrimitive?.doubleOrNull ?: 3.0,
        min_bg = prof["targetLow"]?.jsonPrimitive?.doubleOrNull ?: 100.0,
        max_bg = prof["targetHigh"]?.jsonPrimitive?.doubleOrNull ?: 100.0,
        target_bg = ((prof["targetLow"]?.jsonPrimitive?.doubleOrNull ?: 100.0) +
                     (prof["targetHigh"]?.jsonPrimitive?.doubleOrNull ?: 100.0)) / 2,
        carb_ratio = prof["carbRatio"]?.jsonPrimitive?.doubleOrNull ?: 10.0,
        sens = prof["sensitivity"]?.jsonPrimitive?.doubleOrNull ?: 50.0,
        autosens_adjust_targets = false,
        max_daily_safety_multiplier = 3.0,
        current_basal_safety_multiplier = 4.0,
        high_temptarget_raises_sensitivity = false,
        low_temptarget_lowers_sensitivity = false,
        sensitivity_raises_target = false,
        resistance_lowers_target = false,
        adv_target_adjustments = false,
        exercise_mode = false,
        half_basal_exercise_target = 160,
        maxCOB = 120,
        skip_neutral_temps = false,
        remainingCarbsCap = 90,
        enableUAM = prof["enableUAM"]?.jsonPrimitive?.booleanOrNull ?: false,
        A52_risk_enable = false,
        SMBInterval = prof["smbInterval"]?.jsonPrimitive?.intOrNull ?: 3,
        enableSMB_with_COB = prof["enableSMB"]?.jsonPrimitive?.booleanOrNull ?: false,
        enableSMB_with_temptarget = false,
        allowSMB_with_high_temptarget = false,
        enableSMB_always = prof["enableSMB"]?.jsonPrimitive?.booleanOrNull ?: false,
        enableSMB_after_carbs = false,
        maxSMBBasalMinutes = prof["maxSMBBasalMinutes"]?.jsonPrimitive?.intOrNull ?: 30,
        maxUAMSMBBasalMinutes = prof["maxUAMSMBBasalMinutes"]?.jsonPrimitive?.intOrNull ?: 30,
        bolus_increment = prof["bolusIncrement"]?.jsonPrimitive?.doubleOrNull ?: 0.1,
        carbsReqThreshold = 1,
        current_basal = basalRate,
        temptargetSet = false,
        autosens_max = 1.2,
        out_units = prof["units"]?.jsonPrimitive?.contentOrNull ?: "mg/dL",
        lgsThreshold = null,
        variable_sens = 0.0,
        insulinDivisor = 0,
        TDD = 0.0
    )

    val autosensData = AutosensResult(
        ratio = autosens["ratio"]?.jsonPrimitive?.doubleOrNull ?: 1.0
    )

    val mealData = MealData(
        carbs = meal["carbs"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
        mealCOB = meal["cob"]?.jsonPrimitive?.doubleOrNull
            ?: meal["mealCOB"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
        slopeFromMaxDeviation = meal["slopeFromMaxDeviation"]?.jsonPrimitive?.doubleOrNull ?: 0.0,
        slopeFromMinDeviation = meal["slopeFromMinDeviation"]?.jsonPrimitive?.doubleOrNull ?: 999.0,
        lastCarbTime = meal["lastCarbTime"]?.jsonPrimitive?.longOrNull
            ?: (gsTimestamp - 2 * 60 * 60 * 1000)
    )

    val microBolusAllowed = input["microBolusAllowed"]?.jsonPrimitive?.booleanOrNull ?: false
    val flatBGsDetected = input["flatBGsDetected"]?.jsonPrimitive?.booleanOrNull ?: false

    val clockStr = input["clock"]?.jsonPrimitive?.contentOrNull
    val currentTime = if (clockStr != null) {
        try { java.time.Instant.parse(clockStr).toEpochMilli() } catch (_: Exception) { gsTimestamp }
    } else gsTimestamp

    return TranslatedInput(
        glucoseStatus, currentTemp, iobData, profile,
        autosensData, mealData, microBolusAllowed, currentTime, flatBGsDetected
    )
}

data class TranslatedInput(
    val glucoseStatus: GlucoseStatusSMB,
    val currentTemp: CurrentTemp,
    val iobData: Array<IobTotal>,
    val profile: OapsProfile,
    val autosensData: AutosensResult,
    val mealData: MealData,
    val microBolusAllowed: Boolean,
    val currentTime: Long,
    val flatBGsDetected: Boolean
)

// ── Output Translation ─────────────────────────────────────────────

fun translateOutput(rt: RT, elapsedMs: Long): AdapterOutput {
    val preds = rt.predBGs
    return AdapterOutput(
        algorithm = AlgorithmInfo("aaps-kotlin", "0.1.0"),
        decision = Decision(
            rate = rt.rate,
            duration = rt.duration,
            smb = rt.units,
            reason = rt.reason.toString()
        ),
        predictions = PredictionOutput(
            eventualBG = rt.eventualBG,
            minPredBG = null,
            iob = preds?.IOB,
            zt = preds?.ZT,
            cob = preds?.COB,
            uam = preds?.UAM,
            acob = preds?.aCOB
        ),
        state = StateOutput(
            iob = rt.IOB ?: 0.0,
            cob = rt.COB ?: 0.0,
            bg = rt.bg ?: 0.0,
            tick = rt.tick ?: "flat",
            insulinReq = rt.insulinReq,
            sensitivityRatio = rt.sensitivityRatio ?: 1.0
        ),
        metadata = MetadataOutput(executionTimeMs = elapsedMs)
    )
}

// ── Mode Handlers ──────────────────────────────────────────────────

fun handleDescribe(): String {
    val desc = buildJsonObject {
        put("name", "aaps-kotlin")
        put("algorithm", "oref0-aaps")
        put("version", "0.1.0")
        put("language", "kotlin")
        put("description", "AAPS DetermineBasalSMB.kt — actual Kotlin algorithm from AndroidAPS")
        putJsonObject("capabilities") {
            put("predictions", true)
            put("smb", true)
            put("acob", true)
            put("effectModifiers", false)
            put("inputValidation", true)
        }
        putJsonArray("modes") { add("execute"); add("validate-input"); add("describe") }
        put("source", "externals/AndroidAPS/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalSMB.kt")
    }
    return json.encodeToString(JsonObject.serializer(), desc)
}

fun handleExecute(input: JsonObject, verbose: Boolean): String {
    val translated = translateInput(input)
    val algo = DetermineBasalSMB(translated.profile.out_units)

    val start = System.nanoTime()
    val result = algo.determine_basal(
        translated.glucoseStatus,
        translated.currentTemp,
        translated.iobData,
        translated.profile,
        translated.autosensData,
        translated.mealData,
        translated.microBolusAllowed,
        translated.currentTime,
        translated.flatBGsDetected,
        dynIsfMode = false
    )
    val elapsedMs = (System.nanoTime() - start) / 1_000_000

    val output = translateOutput(result, elapsedMs)
    return json.encodeToString(AdapterOutput.serializer(), output)
}

fun handleValidateInput(input: JsonObject): String {
    val translated = translateInput(input)
    val nativeInput = mapOf(
        "glucoseStatus" to json.encodeToJsonElement(translated.glucoseStatus),
        "currentTemp" to json.encodeToJsonElement(translated.currentTemp),
        "iobDataLength" to JsonPrimitive(translated.iobData.size),
        "profile" to json.encodeToJsonElement(translated.profile),
        "autosensData" to json.encodeToJsonElement(translated.autosensData),
        "mealData" to json.encodeToJsonElement(translated.mealData),
        "microBolusAllowed" to JsonPrimitive(translated.microBolusAllowed),
        "currentTime" to JsonPrimitive(translated.currentTime),
        "flatBGsDetected" to JsonPrimitive(translated.flatBGsDetected)
    )
    val output = AdapterOutput(
        algorithm = AlgorithmInfo("aaps-kotlin", "0.1.0"),
        decision = Decision(null, null, null, "validate-input mode"),
        predictions = PredictionOutput(null),
        state = StateOutput(0.0, 0.0, 0.0, "flat", null, 1.0),
        metadata = MetadataOutput(
            executionTimeMs = 0,
            nativeInput = JsonObject(nativeInput)
        )
    )
    return json.encodeToString(AdapterOutput.serializer(), output)
}

// ── Main ───────────────────────────────────────────────────────────

fun main() {
    val rawInput = System.`in`.bufferedReader().readText()
    if (rawInput.isBlank()) {
        System.err.println("No input received on stdin")
        System.exit(1)
    }

    try {
        val request = json.decodeFromString(AdapterRequest.serializer(), rawInput)

        val result = when (request.mode) {
            "describe" -> handleDescribe()
            "execute" -> {
                val input = request.input ?: error("execute mode requires 'input' field")
                handleExecute(input, request.verbose)
            }
            "validate-input" -> {
                val input = request.input ?: error("validate-input mode requires 'input' field")
                handleValidateInput(input)
            }
            else -> error("Unknown mode: ${request.mode}")
        }

        println(result)
    } catch (e: Exception) {
        val err = ErrorOutput(
            error = e.message ?: "Unknown error",
            algorithm = AlgorithmInfo("aaps-kotlin", "0.1.0"),
            stack = e.stackTraceToString()
        )
        println(json.encodeToString(ErrorOutput.serializer(), err))
        System.exit(1)
    }
}
