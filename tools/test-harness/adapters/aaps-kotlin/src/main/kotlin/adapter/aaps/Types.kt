// Standalone AAPS data types for cross-validation adapter.
// Extracted from AndroidAPS core/interfaces with Android dependencies removed.
// These are faithful copies of the AAPS types - only @Inject/@Singleton and
// Android-specific serializers are replaced with JVM equivalents.
package adapter.aaps

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import java.text.DateFormat
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

// From core/interfaces/aps/APSResult.kt - just the enum
enum class Algorithm {
    UNKNOWN, AMA, SMB, AUTO_ISF
}

// From core/interfaces/aps/GlucoseStatus.kt
interface GlucoseStatus {
    val glucose: Double
    val noise: Double
    val delta: Double
    val shortAvgDelta: Double
    val longAvgDelta: Double
    val date: Long
}

// From core/interfaces/aps/GlucoseStatusSMB.kt
@Serializable
data class GlucoseStatusSMB(
    override val glucose: Double,
    override val noise: Double = 0.0,
    override val delta: Double = 0.0,
    override val shortAvgDelta: Double = 0.0,
    override val longAvgDelta: Double = 0.0,
    override val date: Long = 0L,
) : GlucoseStatus

// From core/interfaces/aps/IobTotal.kt
@Serializable
data class IobTotal(
    val time: Long,
    var iob: Double = 0.0,
    var activity: Double = 0.0,
    var bolussnooze: Double = 0.0,
    var basaliob: Double = 0.0,
    var netbasalinsulin: Double = 0.0,
    var hightempinsulin: Double = 0.0,
    var lastBolusTime: Long = 0,
    var iobWithZeroTemp: IobTotal? = null,
    var netInsulin: Double = 0.0,
    var extendedBolusInsulin: Double = 0.0,
) {
    companion object
}

// From core/interfaces/aps/CurrentTemp.kt
@Serializable
data class CurrentTemp(
    var duration: Int,
    var rate: Double,
    var minutesrunning: Int? = null
)

// From core/interfaces/aps/MealData.kt
@Serializable
data class MealData(
    var carbs: Double = 0.0,
    var mealCOB: Double = 0.0,
    var slopeFromMaxDeviation: Double = 0.0,
    var slopeFromMinDeviation: Double = 999.0,
    var lastBolusTime: Long = 0,
    var lastCarbTime: Long = 0L,
    var usedMinCarbsImpact: Double = 0.0
)

// From core/interfaces/aps/OapsProfile.kt
@Serializable
data class OapsProfile(
    var dia: Double,
    var min_5m_carbimpact: Double,
    var max_iob: Double,
    var max_daily_basal: Double,
    var max_basal: Double,
    var min_bg: Double,
    var max_bg: Double,
    var target_bg: Double,
    var carb_ratio: Double,
    var sens: Double,
    var autosens_adjust_targets: Boolean,
    var max_daily_safety_multiplier: Double,
    var current_basal_safety_multiplier: Double,
    var high_temptarget_raises_sensitivity: Boolean,
    var low_temptarget_lowers_sensitivity: Boolean,
    var sensitivity_raises_target: Boolean,
    var resistance_lowers_target: Boolean,
    var adv_target_adjustments: Boolean,
    var exercise_mode: Boolean,
    var half_basal_exercise_target: Int,
    var maxCOB: Int,
    var skip_neutral_temps: Boolean,
    var remainingCarbsCap: Int,
    var enableUAM: Boolean,
    var A52_risk_enable: Boolean,
    var SMBInterval: Int,
    var enableSMB_with_COB: Boolean,
    var enableSMB_with_temptarget: Boolean,
    var allowSMB_with_high_temptarget: Boolean,
    var enableSMB_always: Boolean,
    var enableSMB_after_carbs: Boolean,
    var maxSMBBasalMinutes: Int,
    var maxUAMSMBBasalMinutes: Int,
    var bolus_increment: Double,
    var carbsReqThreshold: Int,
    var current_basal: Double,
    var temptargetSet: Boolean,
    var autosens_max: Double,
    var out_units: String,
    var lgsThreshold: Int? = null,
    var variable_sens: Double = 0.0,
    var insulinDivisor: Int = 0,
    var TDD: Double = 0.0
)

// From core/interfaces/aps/AutosensResult.kt
@Serializable
data class AutosensResult(
    var ratio: Double = 1.0,
    var carbsAbsorbed: Double = 0.0,
    var sensResult: String = "autosens not available",
    var pastSensitivity: String = "",
    var ratioLimit: String = "",
    var ratioFromTdd: Double = 1.0,
    var ratioFromCarbs: Double = 1.0
)

// From core/interfaces/aps/Predictions.kt
@Serializable
data class Predictions(
    var IOB: List<Int>? = null,
    var ZT: List<Int>? = null,
    var COB: List<Int>? = null,
    var aCOB: List<Int>? = null,
    var UAM: List<Int>? = null
)

// From core/data/configuration/Constants.kt (only the values we need)
object Constants {
    const val MMOLL_TO_MGDL = 18.0
    const val MGDL_TO_MMOLL = 1.0 / MMOLL_TO_MGDL
    const val ALLOW_SMB_WITH_HIGH_TT = 100
}

// Simplified StringBuilder serializer (replaces Joda-dependent version)
object StringBuilderSerializer : KSerializer<StringBuilder> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("StringBuilder", PrimitiveKind.STRING)
    override fun serialize(encoder: Encoder, value: StringBuilder) = encoder.encodeString(value.toString())
    override fun deserialize(decoder: Decoder): StringBuilder = StringBuilder(decoder.decodeString())
}

object TimestampToIsoSerializer : KSerializer<Long> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("LongToIso", PrimitiveKind.STRING)
    override fun serialize(encoder: Encoder, value: Long) = encoder.encodeString(toISOString(value))
    override fun deserialize(decoder: Decoder): Long = 0L // not needed for adapter output

    fun toISOString(date: Long): String {
        val f: DateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.getDefault())
        f.timeZone = TimeZone.getTimeZone("UTC")
        return f.format(date)
    }
}

// From core/interfaces/aps/RT.kt - with Android/Joda dependencies removed
@Serializable
data class RT(
    var algorithm: Algorithm = Algorithm.UNKNOWN,
    var runningDynamicIsf: Boolean = false,
    @Serializable(with = TimestampToIsoSerializer::class)
    var timestamp: Long? = null,
    val temp: String = "absolute",
    var bg: Double? = null,
    var tick: String? = null,
    var eventualBG: Double? = null,
    var targetBG: Double? = null,
    var snoozeBG: Double? = null,
    var insulinReq: Double? = null,
    var carbsReq: Int? = null,
    var carbsReqWithin: Int? = null,
    var units: Double? = null,
    @Serializable(with = TimestampToIsoSerializer::class)
    var deliverAt: Long? = null,
    var sensitivityRatio: Double? = null,
    @Serializable(with = StringBuilderSerializer::class)
    var reason: StringBuilder = StringBuilder(),
    var duration: Int? = null,
    var rate: Double? = null,
    var predBGs: Predictions? = null,
    var COB: Double? = null,
    var IOB: Double? = null,
    var variable_sens: Double? = null,
    var isfMgdlForCarbs: Double? = null,
    var consoleLog: MutableList<String>? = null,
    var consoleError: MutableList<String>? = null
)
