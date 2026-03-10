package org.nightscout.tests

import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.security.MessageDigest

/**
 * Configuration for Nightscout integration tests
 */
object TestConfig {
    val nightscoutUrl: String = System.getenv("NIGHTSCOUT_URL") ?: "http://localhost:1337"
    val apiSecret: String = System.getenv("API_SECRET") ?: "test_api_secret_12_chars"
    
    val apiSecretHash: String by lazy {
        MessageDigest.getInstance("SHA-1")
            .digest(apiSecret.toByteArray())
            .joinToString("") { "%02x".format(it) }
    }
}

/**
 * HTTP client for Nightscout API - simulates AAPS's upload patterns
 */
class NightscoutClient(
    private val baseUrl: String = TestConfig.nightscoutUrl,
    private val apiSecret: String = TestConfig.apiSecret
) {
    private val client = OkHttpClient()
    private val gson = Gson()
    private val JSON = "application/json".toMediaType()
    
    /**
     * Check if server is available
     */
    fun checkStatus(): Boolean {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/status.json")
            .get()
            .build()
        
        return try {
            client.newCall(request).execute().use { response ->
                response.isSuccessful
            }
        } catch (e: Exception) {
            false
        }
    }
    
    /**
     * POST treatment to Nightscout v1 API
     * Simulates AAPS's upload behavior with identifier
     */
    fun postTreatment(treatment: Map<String, Any?>): Map<String, Any?> {
        val body = gson.toJson(treatment).toRequestBody(JSON)
        
        val request = Request.Builder()
            .url("$baseUrl/api/v1/treatments")
            .header("api-secret", TestConfig.apiSecretHash)
            .header("Content-Type", "application/json")
            .post(body)
            .build()
        
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw RuntimeException("HTTP ${response.code}: ${response.body?.string()}")
            }
            
            val responseBody = response.body?.string() ?: "[]"
            // v1 API returns array even for single treatment
            val type = object : TypeToken<List<Map<String, Any?>>>() {}.type
            val list: List<Map<String, Any?>> = gson.fromJson(responseBody, type)
            return list.firstOrNull() ?: throw RuntimeException("Empty response")
        }
    }
    
    /**
     * POST multiple treatments (batch)
     */
    fun postTreatments(treatments: List<Map<String, Any?>>): List<Map<String, Any?>> {
        val body = gson.toJson(treatments).toRequestBody(JSON)
        
        val request = Request.Builder()
            .url("$baseUrl/api/v1/treatments")
            .header("api-secret", TestConfig.apiSecretHash)
            .header("Content-Type", "application/json")
            .post(body)
            .build()
        
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw RuntimeException("HTTP ${response.code}: ${response.body?.string()}")
            }
            
            val responseBody = response.body?.string() ?: "[]"
            val type = object : TypeToken<List<Map<String, Any?>>>() {}.type
            return gson.fromJson(responseBody, type)
        }
    }
    
    /**
     * GET treatments with query
     */
    fun getTreatments(query: Map<String, String> = emptyMap()): List<Map<String, Any?>> {
        val urlBuilder = StringBuilder("$baseUrl/api/v1/treatments")
        if (query.isNotEmpty()) {
            urlBuilder.append("?")
            urlBuilder.append(query.entries.joinToString("&") { "${it.key}=${it.value}" })
        }
        
        val request = Request.Builder()
            .url(urlBuilder.toString())
            .header("api-secret", TestConfig.apiSecretHash)
            .get()
            .build()
        
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw RuntimeException("HTTP ${response.code}: ${response.body?.string()}")
            }
            
            val responseBody = response.body?.string() ?: "[]"
            val type = object : TypeToken<List<Map<String, Any?>>>() {}.type
            return gson.fromJson(responseBody, type)
        }
    }
    
    /**
     * DELETE treatment by _id
     */
    fun deleteTreatment(id: String) {
        val request = Request.Builder()
            .url("$baseUrl/api/v1/treatments/$id")
            .header("api-secret", TestConfig.apiSecretHash)
            .delete()
            .build()
        
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw RuntimeException("HTTP ${response.code}: ${response.body?.string()}")
            }
        }
    }
}
