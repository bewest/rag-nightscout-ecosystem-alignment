import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
import Crypto

/// Configuration for Nightscout integration tests
public struct TestConfig {
    public static var nightscoutURL: String {
        ProcessInfo.processInfo.environment["NIGHTSCOUT_URL"] ?? "http://localhost:1337"
    }
    
    public static var apiSecret: String {
        ProcessInfo.processInfo.environment["API_SECRET"] ?? "test_api_secret_12_chars"
    }
    
    /// SHA1 hash of API secret (for api-secret header)
    public static var apiSecretHash: String {
        sha1(apiSecret)
    }
    
    private static func sha1(_ string: String) -> String {
        let data = Data(string.utf8)
        let digest = Insecure.SHA1.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}

/// Errors from Nightscout API calls
public enum NightscoutError: Error {
    case invalidURL
    case httpError(statusCode: Int, body: String)
    case decodingError(String)
    case networkError(Error)
}

/// HTTP client for Nightscout API - simulates Loop's upload patterns
public class NightscoutClient {
    public let baseURL: URL
    public let apiSecret: String
    private let session: URLSession
    
    public init(baseURL: String = TestConfig.nightscoutURL, apiSecret: String = TestConfig.apiSecret) {
        self.baseURL = URL(string: baseURL)!
        self.apiSecret = apiSecret
        self.session = URLSession.shared
    }
    
    /// POST treatment to Nightscout v1 API
    /// Simulates Loop's upload behavior with UUID _id
    public func postTreatment(_ treatment: [String: Any]) async throws -> [String: Any] {
        let url = baseURL.appendingPathComponent("/api/v1/treatments")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(TestConfig.apiSecretHash, forHTTPHeaderField: "api-secret")
        request.httpBody = try JSONSerialization.data(withJSONObject: treatment)
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw NightscoutError.networkError(URLError(.badServerResponse))
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            throw NightscoutError.httpError(statusCode: httpResponse.statusCode, body: String(data: data, encoding: .utf8) ?? "")
        }
        
        // v1 API returns array even for single treatment
        guard let jsonArray = try JSONSerialization.jsonObject(with: data) as? [[String: Any]],
              let json = jsonArray.first else {
            throw NightscoutError.decodingError("Expected array response with at least one treatment")
        }
        
        return json
    }
    
    /// POST multiple treatments (batch)
    public func postTreatments(_ treatments: [[String: Any]]) async throws -> [[String: Any]] {
        let url = baseURL.appendingPathComponent("/api/v1/treatments")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(TestConfig.apiSecretHash, forHTTPHeaderField: "api-secret")
        request.httpBody = try JSONSerialization.data(withJSONObject: treatments)
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw NightscoutError.networkError(URLError(.badServerResponse))
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            throw NightscoutError.httpError(statusCode: httpResponse.statusCode, body: String(data: data, encoding: .utf8) ?? "")
        }
        
        guard let json = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            throw NightscoutError.decodingError("Expected array response")
        }
        
        return json
    }
    
    /// GET treatments with query
    public func getTreatments(query: [String: String] = [:]) async throws -> [[String: Any]] {
        var components = URLComponents(url: baseURL.appendingPathComponent("/api/v1/treatments"), resolvingAgainstBaseURL: false)!
        components.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        
        var request = URLRequest(url: components.url!)
        request.httpMethod = "GET"
        request.setValue(TestConfig.apiSecretHash, forHTTPHeaderField: "api-secret")
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw NightscoutError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0, body: String(data: data, encoding: .utf8) ?? "")
        }
        
        guard let json = try JSONSerialization.jsonObject(with: data) as? [[String: Any]] else {
            throw NightscoutError.decodingError("Expected array response")
        }
        
        return json
    }
    
    /// DELETE treatment by _id
    public func deleteTreatment(id: String) async throws {
        let url = baseURL.appendingPathComponent("/api/v1/treatments/\(id)")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue(TestConfig.apiSecretHash, forHTTPHeaderField: "api-secret")
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw NightscoutError.httpError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0, body: String(data: data, encoding: .utf8) ?? "")
        }
    }
    
    /// Check server status
    public func checkStatus() async throws -> Bool {
        let url = baseURL.appendingPathComponent("/api/v1/status.json")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        
        let (data, response) = try await session.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            return false
        }
        
        guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let status = json["status"] as? String else {
            return false
        }
        
        return status == "ok"
    }
}

/// Simulates Loop's ObjectIdCache behavior
/// Maps syncIdentifier (UUID) to server-assigned ObjectId
public class ObjectIdCache {
    private var cache: [String: String] = [:]
    
    public init() {}
    
    public func store(syncIdentifier: String, objectId: String) {
        cache[syncIdentifier] = objectId
    }
    
    public func findObjectId(for syncIdentifier: String) -> String? {
        cache[syncIdentifier]
    }
    
    public func clear() {
        cache.removeAll()
    }
}
