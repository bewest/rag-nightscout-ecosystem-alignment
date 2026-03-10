package org.nightscout.tests

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Assumptions.assumeTrue
import java.util.UUID
import java.time.Instant
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull

/**
 * Tests simulating AAPS's Bolus upload behavior
 * 
 * AAPS uses `identifier` field (not `_id`):
 * ```kotlin
 * // From BolusExtension.kt
 * identifier = bolus.ids.nightscoutId  // Or generate UUID
 * ```
 * 
 * PR #8447/Option G behavior:
 * - Server uses `identifier` for deduplication
 * - Server generates ObjectId for `_id`
 * - Response includes both fields
 */
class BolusUploadTest {
    
    private lateinit var client: NightscoutClient
    
    @BeforeEach
    fun setUp() {
        client = NightscoutClient()
        assumeTrue(client.checkStatus(), "Nightscout server not available at ${TestConfig.nightscoutUrl}")
    }
    
    /**
     * Test: POST bolus with identifier (AAPS pattern)
     * 
     * Simulates: AAPS uploads new Bolus treatment
     * Expected (PR #8447/Option G):
     * - `identifier` preserved as-is
     * - `_id` = server-generated ObjectId (24 hex chars)
     */
    @Test
    fun testPostBolusWithIdentifier() {
        val identifier = UUID.randomUUID().toString()
        
        val bolus = mapOf(
            "identifier" to identifier,
            "eventType" to "Bolus",
            "insulin" to 2.5,
            "created_at" to Instant.now().toString()
        )
        
        val response = client.postTreatment(bolus)
        
        // identifier preserved
        assertEquals(identifier, response["identifier"], "identifier should be preserved")
        
        // _id is ObjectId (24 hex chars)
        val objectId = response["_id"] as? String
        assertNotNull(objectId, "_id should be present")
        assertEquals(24, objectId.length, "_id should be 24-char ObjectId")
        
        // Cleanup
        client.deleteTreatment(objectId)
    }
    
    /**
     * Test: SMB bolus upload (TEST-AAPS-BOLUS-001)
     * 
     * AAPS uses type: SMB for Super Micro Bolus
     * From NSBolus.kt: enum class BolusType { NORMAL, SMB, PRIMING }
     */
    @Test
    fun testSmbBolusUpload() {
        val identifier = UUID.randomUUID().toString()
        
        val smb = mapOf(
            "identifier" to identifier,
            "eventType" to "Bolus",
            "insulin" to 0.3,  // SMBs are typically small
            "type" to "SMB",
            "isSMB" to true,
            "created_at" to Instant.now().toString()
        )
        
        val response = client.postTreatment(smb)
        
        assertEquals(identifier, response["identifier"])
        assertEquals("SMB", response["type"])
        assertEquals(true, response["isSMB"])
        assertEquals(0.3, response["insulin"])
        
        val objectId = response["_id"] as String
        assertEquals(24, objectId.length)
        
        // Cleanup
        client.deleteTreatment(objectId)
    }
    
    /**
     * Test: Re-upload same bolus deduplicates
     * 
     * Simulates: AAPS retries after network failure
     * Expected: Upsert by `identifier`, no duplicate created
     */
    @Test
    fun testReuploadBolusDeduplicates() {
        val identifier = UUID.randomUUID().toString()
        
        val bolus = mapOf(
            "identifier" to identifier,
            "eventType" to "Bolus",
            "insulin" to 2.5,
            "created_at" to Instant.now().toString()
        )
        
        // First upload
        val response1 = client.postTreatment(bolus)
        val objectId1 = response1["_id"] as? String
        
        // Second upload (same identifier) - should upsert
        val updatedBolus = bolus + ("insulin" to 3.0)
        val response2 = client.postTreatment(updatedBolus)
        val objectId2 = response2["_id"] as? String
        
        // Should get same ObjectId (upserted, not duplicated)
        assertEquals(objectId1, objectId2, "Re-upload should upsert to same document")
        
        // Query - should only find one
        val results = client.getTreatments(mapOf("find[identifier]" to identifier))
        assertEquals(1, results.size, "Should have exactly one treatment (deduped)")
        assertEquals(3.0, results.first()["insulin"], "Should have updated insulin")
        
        // Cleanup
        client.deleteTreatment(objectId1!!)
    }
    
    /**
     * Test: Bolus with pump correlation (AAPS pattern)
     * 
     * AAPS includes pump-specific fields:
     * - pumpId: Unique ID from pump
     * - pumpType: e.g., "OMNIPOD_DASH"
     * - pumpSerial: Pump serial number
     */
    @Test
    fun testBolusWithPumpCorrelation() {
        val identifier = UUID.randomUUID().toString()
        val pumpId = "DASH-${System.currentTimeMillis()}"
        
        val bolus = mapOf(
            "identifier" to identifier,
            "eventType" to "Bolus",
            "insulin" to 1.5,
            "pumpId" to pumpId,
            "pumpType" to "OMNIPOD_DASH",
            "pumpSerial" to "PDM12345",
            "created_at" to Instant.now().toString()
        )
        
        val response = client.postTreatment(bolus)
        
        // All fields preserved
        assertEquals(identifier, response["identifier"])
        assertEquals(pumpId, response["pumpId"])
        assertEquals("OMNIPOD_DASH", response["pumpType"])
        assertEquals("PDM12345", response["pumpSerial"])
        
        // Cleanup
        client.deleteTreatment(response["_id"] as String)
    }
    
    /**
     * Test: Temp Target with identifier (like Loop override)
     * 
     * AAPS TemporaryTarget is equivalent to Loop's Temporary Override
     */
    @Test
    fun testTempTargetWithIdentifier() {
        val identifier = UUID.randomUUID().toString()
        
        val tempTarget = mapOf(
            "identifier" to identifier,
            "eventType" to "Temporary Target",
            "reason" to "Activity",
            "targetTop" to 140,
            "targetBottom" to 120,
            "duration" to 60,
            "created_at" to Instant.now().toString()
        )
        
        val response = client.postTreatment(tempTarget)
        
        assertEquals(identifier, response["identifier"])
        assertEquals("Temporary Target", response["eventType"])
        
        val objectId = response["_id"] as String
        assertEquals(24, objectId.length)
        
        // Cleanup
        client.deleteTreatment(objectId)
    }
    
    /**
     * Test: Batch upload with identifiers
     * 
     * Simulates: AAPS uploads multiple treatments at once
     * Expected: All identifiers preserved, response in same order
     */
    @Test
    fun testBatchUploadWithIdentifiers() {
        val identifiers = (0..<3).map { UUID.randomUUID().toString() }
        
        val treatments = identifiers.mapIndexed { index, id ->
            mapOf(
                "identifier" to id,
                "eventType" to "Bolus",
                "insulin" to (1.0 + index * 0.5),
                "created_at" to Instant.now().plusSeconds(index.toLong()).toString()
            )
        }
        
        val responses = client.postTreatments(treatments)
        
        assertEquals(3, responses.size, "Should return 3 treatments")
        
        // Verify identifiers preserved (order preserved)
        responses.forEachIndexed { index, response ->
            assertEquals(identifiers[index], response["identifier"], "identifier $index should match")
            assertEquals(24, (response["_id"] as String).length, "_id should be ObjectId")
        }
        
        // Cleanup
        responses.forEach { client.deleteTreatment(it["_id"] as String) }
    }
}
