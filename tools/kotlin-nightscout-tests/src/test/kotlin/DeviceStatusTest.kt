package org.nightscout.tests

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Assumptions.assumeTrue
import java.time.Instant
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

/**
 * Tests for AAPS DeviceStatus uploads (TEST-AAPS-DS-*)
 * 
 * DeviceStatus contains openaps algorithm state and pump info
 */
class DeviceStatusTest {
    
    private lateinit var client: NightscoutClient
    
    @BeforeEach
    fun setUp() {
        client = NightscoutClient()
        assumeTrue(client.checkStatus(), "Nightscout server not available")
    }
    
    /**
     * Test: AAPS status upload (TEST-AAPS-DS-001)
     * 
     * AAPS uploads openaps.* and pump.* fields
     */
    @Test
    fun testAapsDeviceStatus() {
        val deviceStatus = mapOf(
            "device" to "openaps://AAPS",
            "created_at" to Instant.now().toString(),
            "openaps" to mapOf(
                "iob" to mapOf(
                    "iob" to 2.5,
                    "basaliob" to 1.2,
                    "activity" to 0.015
                ),
                "enacted" to mapOf(
                    "bg" to 120,
                    "eventualBG" to 110,
                    "reason" to "COB: 30, IOB: 2.5"
                )
            ),
            "pump" to mapOf(
                "battery" to mapOf("percent" to 85),
                "reservoir" to 150.5,
                "status" to mapOf("status" to "normal")
            )
        )
        
        val response = client.postDeviceStatus(deviceStatus)
        
        assertNotNull(response["_id"])
        assertEquals("openaps://AAPS", response["device"])
        
        @Suppress("UNCHECKED_CAST")
        val openaps = response["openaps"] as? Map<String, Any?>
        assertNotNull(openaps)
        
        @Suppress("UNCHECKED_CAST")
        val iob = openaps["iob"] as? Map<String, Any?>
        assertEquals(2.5, iob?.get("iob"))
        
        // Cleanup
        client.deleteDeviceStatus(response["_id"] as String)
    }
    
    /**
     * Test: SMB prediction data (TEST-AAPS-DS-002)
     */
    @Test
    fun testSmbPrediction() {
        val deviceStatus = mapOf(
            "device" to "openaps://AAPS",
            "created_at" to Instant.now().toString(),
            "openaps" to mapOf(
                "suggested" to mapOf(
                    "bg" to 130,
                    "eventualBG" to 95,
                    "insulinReq" to 0.3,
                    "units" to 0.1,
                    "deliverAt" to Instant.now().toString(),
                    "reason" to "SMB needed"
                )
            )
        )
        
        val response = client.postDeviceStatus(deviceStatus)
        
        assertNotNull(response["_id"])
        
        @Suppress("UNCHECKED_CAST")
        val openaps = response["openaps"] as? Map<String, Any?>
        @Suppress("UNCHECKED_CAST")
        val suggested = openaps?.get("suggested") as? Map<String, Any?>
        assertEquals(0.1, suggested?.get("units"))
        
        client.deleteDeviceStatus(response["_id"] as String)
    }
    
    /**
     * Test: Pump reservoir/battery (TEST-AAPS-DS-003)
     */
    @Test
    fun testPumpStatus() {
        val deviceStatus = mapOf(
            "device" to "openaps://AAPS",
            "created_at" to Instant.now().toString(),
            "pump" to mapOf(
                "battery" to mapOf("percent" to 72),
                "reservoir" to 85.0,
                "clock" to Instant.now().toString(),
                "status" to mapOf(
                    "status" to "normal",
                    "bolusing" to false,
                    "suspended" to false
                )
            )
        )
        
        val response = client.postDeviceStatus(deviceStatus)
        
        assertNotNull(response["_id"])
        
        @Suppress("UNCHECKED_CAST")
        val pump = response["pump"] as? Map<String, Any?>
        assertEquals(85.0, pump?.get("reservoir"))
        
        @Suppress("UNCHECKED_CAST")
        val battery = pump?.get("battery") as? Map<String, Any?>
        assertEquals(72.0, battery?.get("percent"))
        
        client.deleteDeviceStatus(response["_id"] as String)
    }
}
