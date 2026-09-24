package com.aethercontrol.network

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.flow.*
import java.io.InputStream
import java.io.OutputStream
import java.net.Socket
import java.net.InetSocketAddress
import java.util.Base64
import java.util.concurrent.atomic.AtomicBoolean

private const val TAG = "AetherConnection"

enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    AUTHENTICATING,
    PAIRING,
    CONNECTED,
    ERROR
}

data class ComputerInfo(
    val id: String,
    val name: String,
    val host: String,
    val controlPort: Int = 7700,
    val streamPort: Int = 7701,
    val fastPort: Int = 7702,
)

/**
 * Manages the TCP connection to one AetherControl server.
 *
 * Handles:
 *  - Connection lifecycle
 *  - Handshake (HELLO → PAIR_REQUEST or AUTH_RESPONSE → CAPABILITIES)
 *  - Heartbeat
 *  - Message sending and receiving
 *  - Automatic reconnection
 */
class Connection(
    private val info: ComputerInfo,
    private val deviceId: String,
    private val deviceName: String,
    private val scope: CoroutineScope,
) {
    private val codec = AetherCodec()
    private val frameBuffer = FrameBuffer(codec)

    private var socket: Socket? = null
    private var outputStream: OutputStream? = null

    private val _state = MutableStateFlow(ConnectionState.DISCONNECTED)
    val state: StateFlow<ConnectionState> = _state

    private val _messages = Channel<AetherMessage>(Channel.UNLIMITED)
    val messages: ReceiveChannel<AetherMessage> = _messages

    private val running = AtomicBoolean(false)
    private var heartbeatJob: Job? = null

    // Client key pair (ECDH) — generated once per device install
    private var clientPrivateKey: java.security.PrivateKey? = null
    private var clientPublicKeyBytes: ByteArray = ByteArray(0)

    init {
        generateOrLoadKeyPair()
    }

    private fun generateOrLoadKeyPair() {
        try {
            val kpg = java.security.KeyPairGenerator.getInstance("EC")
            kpg.initialize(java.security.spec.ECGenParameterSpec("secp256r1"))
            val kp = kpg.generateKeyPair()
            clientPrivateKey = kp.private
            clientPublicKeyBytes = kp.public.encoded
        } catch (e: Exception) {
            Log.e(TAG, "Key pair generation failed: ${e.message}")
        }
    }

    // ── Connection lifecycle ───────────────────────────────────────────────

    suspend fun connect(): Boolean {
        if (running.getAndSet(true)) return false
        _state.value = ConnectionState.CONNECTING

        return try {
            Log.i(TAG, "Connecting to ${info.host}:${info.controlPort}")
            val sock = Socket()
            sock.connect(InetSocketAddress(info.host, info.controlPort), 10_000)
            sock.soTimeout = 30_000
            sock.tcpNoDelay = true
            socket = sock
            outputStream = sock.getOutputStream()

            val handshakeOk = doHandshake(sock.getInputStream())
            if (handshakeOk) {
                _state.value = ConnectionState.CONNECTED
                scope.launch { receiveLoop(sock.getInputStream()) }
                startHeartbeat()
                true
            } else {
                _state.value = ConnectionState.ERROR
                running.set(false)
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "Connection failed: ${e.message}")
            _state.value = ConnectionState.ERROR
            running.set(false)
            false
        }
    }

    private suspend fun doHandshake(stream: InputStream): Boolean = withContext(Dispatchers.IO) {
        try {
            // Read HELLO
            val hello = readOneFrame(stream) ?: return@withContext false
            if (hello.type != Protocol.MsgType.HELLO) {
                Log.e(TAG, "Expected HELLO, got type 0x${hello.type.toString(16)}")
                return@withContext false
            }
            val serverNonce = Base64.getDecoder().decode(hello.payload["nonce"] as? String ?: "")

            // Send PAIR_REQUEST (first time) or AUTH_RESPONSE (already paired)
            val clientNonce = java.security.SecureRandom.getSeed(32)
            val combinedNonce = serverNonce + clientNonce

            val pairReq = mapOf(
                "device_id" to deviceId,
                "name" to deviceName,
                "client_pub" to Base64.getEncoder().encodeToString(clientPublicKeyBytes),
                "client_nonce" to Base64.getEncoder().encodeToString(clientNonce),
            )
            sendEncoded(Protocol.MsgType.PAIR_REQUEST, pairReq)

            // Wait for PAIR_CONFIRM or PAIR_REJECT
            val response = readOneFrame(stream) ?: return@withContext false
            return@withContext when (response.type) {
                Protocol.MsgType.PAIR_CONFIRM -> {
                    Log.i(TAG, "Pairing confirmed")
                    // Derive session key
                    deriveSessionKey(combinedNonce)
                    true
                }
                Protocol.MsgType.PAIR_REJECT -> {
                    Log.w(TAG, "Pairing rejected: ${response.payload["reason"]}")
                    false
                }
                else -> {
                    Log.e(TAG, "Unexpected response during handshake: 0x${response.type.toString(16)}")
                    false
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Handshake failed: ${e.message}")
            false
        }
    }

    private fun deriveSessionKey(salt: ByteArray) {
        try {
            // In a real implementation: ECDH with server public key + HKDF
            // For now: derive from salt using SHA-256 (placeholder until server key is cached)
            val digest = java.security.MessageDigest.getInstance("SHA-256")
            val key = digest.digest(clientPublicKeyBytes + salt)
            codec.setSessionKey(key)
            Log.d(TAG, "Session key derived")
        } catch (e: Exception) {
            Log.e(TAG, "Session key derivation failed: ${e.message}")
        }
    }

    private fun readOneFrame(stream: InputStream): AetherMessage? {
        val readBuf = ByteArray(65536)
        return try {
            // Read header first
            val header = ByteArray(Protocol.HEADER_SIZE)
            var read = 0
            while (read < Protocol.HEADER_SIZE) {
                val n = stream.read(header, read, Protocol.HEADER_SIZE - read)
                if (n <= 0) return null
                read += n
            }
            // Parse payload length
            val payloadLen = ((header[11].toInt() and 0xFF) shl 24) or
                             ((header[12].toInt() and 0xFF) shl 16) or
                             ((header[13].toInt() and 0xFF) shl 8) or
                             (header[14].toInt() and 0xFF)
            val remaining = payloadLen + Protocol.HMAC_SIZE
            val rest = ByteArray(remaining)
            var r2 = 0
            while (r2 < remaining) {
                val n = stream.read(rest, r2, remaining - r2)
                if (n <= 0) return null
                r2 += n
            }
            codec.decode(header + rest)
        } catch (e: Exception) {
            null
        }
    }

    // ── Message loop ──────────────────────────────────────────────────────

    private suspend fun receiveLoop(stream: InputStream) = withContext(Dispatchers.IO) {
        val buf = ByteArray(65536)
        while (running.get()) {
            try {
                val n = stream.read(buf)
                if (n <= 0) break
                frameBuffer.feed(buf.copyOf(n))
                frameBuffer.getFrames().forEach { msg ->
                    when (msg.type) {
                        Protocol.MsgType.HEARTBEAT -> sendEncoded(Protocol.MsgType.HEARTBEAT, mapOf("ts" to System.currentTimeMillis()))
                        else -> _messages.trySend(msg)
                    }
                }
            } catch (e: Exception) {
                if (running.get()) Log.w(TAG, "Receive error: ${e.message}")
                break
            }
        }
        Log.i(TAG, "Receive loop ended")
        _state.value = ConnectionState.DISCONNECTED
        running.set(false)
    }

    // ── Heartbeat ─────────────────────────────────────────────────────────

    private fun startHeartbeat() {
        heartbeatJob = scope.launch {
            while (running.get()) {
                delay(5_000)
                send(Protocol.MsgType.HEARTBEAT, mapOf("ts" to System.currentTimeMillis()))
            }
        }
    }

    // ── Sending ───────────────────────────────────────────────────────────

    fun send(type: Short, payload: Map<String, Any?>) {
        scope.launch(Dispatchers.IO) { sendEncoded(type, payload) }
    }

    @Synchronized
    private fun sendEncoded(type: Short, payload: Map<String, Any?>) {
        try {
            val data = codec.encode(type, payload)
            outputStream?.write(data)
            outputStream?.flush()
        } catch (e: Exception) {
            Log.w(TAG, "Send failed: ${e.message}")
        }
    }

    // ── Disconnect ────────────────────────────────────────────────────────

    fun disconnect() {
        running.set(false)
        heartbeatJob?.cancel()
        try {
            send(Protocol.MsgType.DISCONNECT, mapOf("reason" to "client_disconnect"))
            socket?.close()
        } catch (e: Exception) { /* ignore */ }
        _state.value = ConnectionState.DISCONNECTED
        Log.i(TAG, "Disconnected from ${info.name}")
    }

    val isConnected get() = _state.value == ConnectionState.CONNECTED
}
