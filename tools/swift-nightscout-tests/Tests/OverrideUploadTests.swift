import XCTest
@testable import NightscoutTestKit

/// Tests simulating Loop's Temporary Override upload behavior
///
/// Loop overrides are unique - they send UUID directly as `_id`:
/// ```swift
/// // From OverrideTreament.swift:59
/// id: override.syncIdentifier.uuidString
/// ```
///
/// PR #8447 behavior (Option G - REQ-SYNC-072):
/// - Server moves UUID to `identifier` field
/// - Server generates ObjectId for `_id`
/// - Response includes both fields
final class OverrideUploadTests: XCTestCase {
    
    var client: NightscoutClient!
    
    override func setUp() async throws {
        client = NightscoutClient()
        
        // Skip if server not running
        let available = try await client.checkStatus()
        try XCTSkipUnless(available, "Nightscout server not available at \(TestConfig.nightscoutURL)")
    }
    
    /// Test: POST override with UUID _id (Loop pattern)
    ///
    /// Simulates: Loop uploads new Temporary Override
    /// PR #8447/Option G expects:
    /// - `identifier` = original UUID
    /// - `_id` = server-generated ObjectId (24 hex chars)
    func testPostOverrideWithUUID() async throws {
        let uuid = UUID().uuidString
        
        let override: [String: Any] = [
            "_id": uuid,
            "eventType": "Temporary Override",
            "reason": "Pre-Meal",
            "duration": 60,
            "created_at": ISO8601DateFormatter().string(from: Date())
        ]
        
        let response = try await client.postTreatment(override)
        
        // Option G: UUID moved to identifier, _id is ObjectId
        XCTAssertEqual(response["identifier"] as? String, uuid, "UUID should be promoted to identifier")
        
        let objectId = response["_id"] as? String
        XCTAssertNotNil(objectId, "_id should be present")
        XCTAssertNotEqual(objectId, uuid, "_id should not be UUID")
        XCTAssertEqual(objectId?.count, 24, "_id should be 24-char ObjectId")
        
        // Cleanup using server-assigned ObjectId
        if let objectId = objectId {
            try await client.deleteTreatment(id: objectId)
        }
    }
    
    /// Test: Re-upload same override deduplicates
    ///
    /// Simulates: Loop re-uploads after ObjectIdCache expiry
    /// Expected: Upsert by identifier, no duplicate created
    func testReuploadOverrideDeduplicates() async throws {
        let uuid = UUID().uuidString
        let createdAt = ISO8601DateFormatter().string(from: Date())
        
        let override: [String: Any] = [
            "_id": uuid,
            "eventType": "Temporary Override",
            "reason": "Pre-Meal",
            "duration": 60,
            "created_at": createdAt
        ]
        
        // First upload
        let response1 = try await client.postTreatment(override)
        let objectId1 = response1["_id"] as? String
        
        // Second upload (same UUID) - should upsert via identifier
        var updatedOverride = override
        updatedOverride["reason"] = "Exercise"
        let response2 = try await client.postTreatment(updatedOverride)
        let objectId2 = response2["_id"] as? String
        
        // Should get same ObjectId (upserted, not duplicated)
        XCTAssertEqual(objectId1, objectId2, "Re-upload should upsert to same document")
        
        // Query by identifier - should only find one
        let results = try await client.getTreatments(query: ["find[identifier]": uuid])
        XCTAssertEqual(results.count, 1, "Should have exactly one treatment (deduped)")
        XCTAssertEqual(results.first?["reason"] as? String, "Exercise", "Should have updated reason")
        
        // Cleanup
        if let objectId = objectId1 {
            try await client.deleteTreatment(id: objectId)
        }
    }
    
    /// Test: DELETE override by ObjectId
    ///
    /// Simulates: Loop cancels override using cached ObjectId
    /// Expected: Can delete using server-assigned _id
    func testDeleteOverrideByObjectId() async throws {
        let uuid = UUID().uuidString
        
        let override: [String: Any] = [
            "_id": uuid,
            "eventType": "Temporary Override",
            "reason": "Pre-Meal",
            "duration": 60,
            "created_at": ISO8601DateFormatter().string(from: Date())
        ]
        
        // Create
        let response = try await client.postTreatment(override)
        let objectId = response["_id"] as? String
        XCTAssertNotNil(objectId)
        
        // Delete by ObjectId
        try await client.deleteTreatment(id: objectId!)
        
        // Verify deleted
        let results = try await client.getTreatments(query: ["find[identifier]": uuid])
        XCTAssertEqual(results.count, 0, "Treatment should be deleted")
    }
    
    /// Test: Batch upload with UUIDs
    ///
    /// Simulates: Loop uploads multiple overrides
    /// Expected: All UUIDs promoted to identifier, response in same order
    func testBatchUploadWithUUIDs() async throws {
        let uuids = (0..<3).map { _ in UUID().uuidString }
        
        let overrides: [[String: Any]] = uuids.enumerated().map { index, uuid in
            [
                "_id": uuid,
                "eventType": "Temporary Override",
                "reason": "Override \(index)",
                "duration": 60,
                "created_at": ISO8601DateFormatter().string(from: Date().addingTimeInterval(Double(index)))
            ]
        }
        
        let responses = try await client.postTreatments(overrides)
        
        XCTAssertEqual(responses.count, 3, "Should return 3 treatments")
        
        // Verify UUIDs promoted to identifier (order preserved)
        for (index, response) in responses.enumerated() {
            XCTAssertEqual(response["identifier"] as? String, uuids[index], "identifier \(index) should match UUID")
            XCTAssertEqual((response["_id"] as? String)?.count, 24, "_id should be ObjectId")
        }
        
        // Cleanup
        for response in responses {
            if let objectId = response["_id"] as? String {
                try await client.deleteTreatment(id: objectId)
            }
        }
    }
    
    /// Test: ObjectIdCache workflow simulation
    ///
    /// Simulates: Loop's cache behavior for carbs/boluses
    /// 1. POST without _id, get server ObjectId
    /// 2. Cache mapping: syncIdentifier -> ObjectId
    /// 3. Use ObjectId for subsequent updates
    func testObjectIdCacheWorkflow() async throws {
        let cache = ObjectIdCache()
        let syncIdentifier = UUID().uuidString
        
        // Initial POST without _id (like carbs)
        let treatment: [String: Any] = [
            "eventType": "Carb Correction",
            "carbs": 30,
            "syncIdentifier": syncIdentifier,
            "created_at": ISO8601DateFormatter().string(from: Date())
        ]
        
        let response = try await client.postTreatment(treatment)
        
        // Server assigns ObjectId
        guard let objectId = response["_id"] as? String else {
            XCTFail("Expected _id in response")
            return
        }
        
        // Cache the mapping
        cache.store(syncIdentifier: syncIdentifier, objectId: objectId)
        
        // Verify cache works
        XCTAssertEqual(cache.findObjectId(for: syncIdentifier), objectId)
        
        // Update using cached ObjectId
        var updated = treatment
        updated["_id"] = objectId
        updated["carbs"] = 45
        _ = try await client.postTreatment(updated)
        
        // Verify update
        let results = try await client.getTreatments(query: ["find[_id]": objectId])
        XCTAssertEqual(results.first?["carbs"] as? Int, 45)
        
        // Cleanup
        try await client.deleteTreatment(id: objectId)
    }
    
    /// TEST-OVR-005: Override without syncIdentifier shows UUID in _id only
    func testOverrideWithoutSyncIdentifierField() async throws {
        let uuid = UUID().uuidString
        
        // Loop sends UUID as _id, not as separate syncIdentifier field
        let override: [String: Any] = [
            "_id": uuid,
            "eventType": "Temporary Override",
            "reason": "Exercise",
            "duration": 60,
            "created_at": ISO8601DateFormatter().string(from: Date())
        ]
        
        let response = try await client.postTreatment(override)
        
        // PR #8447 promotes UUID _id to identifier
        XCTAssertEqual(response["identifier"] as? String, uuid)
        
        // Original _id is NOT a syncIdentifier field
        XCTAssertNil(response["syncIdentifier"], "No separate syncIdentifier field")
        
        // Cleanup
        let objectId = response["_id"] as! String
        try await client.deleteTreatment(id: objectId)
    }
    
    /// TEST-OVR-006: Cancel indefinite override
    func testCancelIndefiniteOverride() async throws {
        let uuid = UUID().uuidString
        
        // Create indefinite override
        let override: [String: Any] = [
            "_id": uuid,
            "eventType": "Temporary Override",
            "reason": "Sick Day",
            "durationType": "indefinite",
            "created_at": ISO8601DateFormatter().string(from: Date())
        ]
        
        let response = try await client.postTreatment(override)
        let objectId = response["_id"] as! String
        
        // Verify created
        XCTAssertEqual(response["durationType"] as? String, "indefinite")
        
        // Delete to cancel
        try await client.deleteTreatment(id: objectId)
        
        // Verify deleted
        let results = try await client.getTreatments(query: ["find[identifier]": uuid])
        XCTAssertTrue(results.isEmpty, "Override should be deleted")
    }
}
