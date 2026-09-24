package com.aethercontrol.network

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.MulticastSocket

private const val TAG = "AetherDiscovery"
private const val DISCOVERY_PORT = 7699
private const val DISCOVERY_MAGIC = "AETHER_SERVER"
private const val DISCOVERY_TIMEOUT_MS = 3000L

/**
 * Discovers AetherControl servers on the local network.
 *
 * Methods:
 * 1. UDP broadcast listener (primary — matches server's broadcast)
 * 2. mDNS via NsdManager (Android's built-in service discovery)
 */
class DiscoveryClient(private val scope: CoroutineScope) {

    private val _discovered = MutableStateFlow<List<ComputerInfo>>(emptyList())
    val discovered: StateFlow<List<ComputerInfo>> = _discovered

    private var discoveryJob: Job? = null
    private val seen = mutableSetOf<String>()  // server_id dedup set

    fun startDiscovery() {
        discoveryJob?.cancel()
        discoveryJob = scope.launch {
            listenForBroadcasts()
        }
        Log.i(TAG, "Discovery started")
    }

    fun stopDiscovery() {
        discoveryJob?.cancel()
        Log.i(TAG, "Discovery stopped")
    }

    fun clearDiscovered() {
        _discovered.value = emptyList()
        seen.clear()
    }

    private suspend fun listenForBroadcasts() = withContext(Dispatchers.IO) {
        try {
            val socket = DatagramSocket(DISCOVERY_PORT).also {
                it.soTimeout = DISCOVERY_TIMEOUT_MS.toInt()
                it.broadcast = true
            }
            val buf = ByteArray(4096)
            val packet = DatagramPacket(buf, buf.size)

            Log.d(TAG, "Listening for UDP broadcasts on port $DISCOVERY_PORT")
            while (isActive) {
                try {
                    socket.receive(packet)
                    val json = String(packet.data, 0, packet.length, Charsets.UTF_8)
                    parseAnnouncement(json, packet.address.hostAddress ?: "")
                } catch (e: java.net.SocketTimeoutException) {
                    // Expected; continue listening
                } catch (e: Exception) {
                    Log.w(TAG, "Receive error: ${e.message}")
                }
            }
            socket.close()
        } catch (e: Exception) {
            Log.e(TAG, "Discovery listen failed: ${e.message}")
        }
    }

    private fun parseAnnouncement(json: String, sourceIp: String) {
        try {
            val obj = JSONObject(json)
            if (obj.optString("type") != DISCOVERY_MAGIC) return

            val serverId = obj.getString("server_id")
            if (serverId in seen) return
            seen.add(serverId)

            val info = ComputerInfo(
                id          = serverId,
                name        = obj.getString("name"),
                host        = obj.optString("host", sourceIp),
                controlPort = obj.optInt("control_port", 7700),
                streamPort  = obj.optInt("stream_port", 7701),
                fastPort    = obj.optInt("fast_port", 7702),
            )

            Log.i(TAG, "Discovered: ${info.name} @ ${info.host}:${info.controlPort}")
            _discovered.update { it + info }
        } catch (e: Exception) {
            Log.d(TAG, "Failed to parse announcement: ${e.message}")
        }
    }

    /**
     * Attempt manual connection by IP/port (returns ComputerInfo or null if unreachable).
     */
    suspend fun tryManualConnect(host: String, port: Int): ComputerInfo? = withContext(Dispatchers.IO) {
        try {
            val addr = InetAddress.getByName(host)
            if (!addr.isReachable(3000)) return@withContext null
            ComputerInfo(
                id = "manual-$host",
                name = host,
                host = host,
                controlPort = port,
            )
        } catch (e: Exception) {
            null
        }
    }
}
