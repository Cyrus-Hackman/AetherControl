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

    private val _lastErrorMessage = MutableStateFlow<String?>(null)
    val lastErrorMessage: StateFlow<String?> = _lastErrorMessage

    private val _messages = Channel<AetherMessage>(Channel.UNLIMITED)
    val messages: ReceiveChannel<AetherMessage> = _messages

    private val _messagesFlow = MutableSharedFlow<AetherMessage>(
        extraBufferCapacity = 128,
        onBufferOverflow = kotlinx.coroutines.channels.BufferOverflow.DROP_OLDEST
    )
    val messagesFlow: SharedFlow<AetherMessage> = _messagesFlow.asSharedFlow()

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

    suspend fun connect(): Boolean = withContext(Dispatchers.IO) {
        if (running.getAndSet(true)) return@withContext false
        _state.value = ConnectionState.CONNECTING
        _lastErrorMessage.value = null

        try {
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
            Log.e(TAG, "Connection failed: ${e.message}", e)
            _lastErrorMessage.value = "Could not connect to ${info.name} (${info.host}:${info.controlPort}): ${e.localizedMessage ?: "Host unreachable"}"
            _state.value = ConnectionState.ERROR
            running.set(false)
            false
        }
    }

    private suspend fun doHandshake(stream: InputStream): Boolean = withContext(Dispatchers.IO) {
        try {
            // Read HELLO
            val hello = readOneFrame(stream)
            if (hello == null) {
                _lastErrorMessage.value = "Handshake failed: No HELLO frame received from ${info.name}."
                return@withContext false
            }
            if (hello.type != Protocol.MsgType.HELLO) {
                Log.e(TAG, "Expected HELLO, got type 0x${hello.type.toString(16)}")
                _lastErrorMessage.value = "Protocol error: expected HELLO from server, got 0x${hello.type.toString(16)}"
                return@withContext false
            }
            val serverNonce = Base64.getDecoder().decode(hello.payload["nonce"] as? String ?: "")
            // Read the server's ECDH public key (DER SubjectPublicKeyInfo, base64-encoded)
            val serverPubB64 = hello.payload["server_pub"] as? String ?: ""
            if (serverPubB64.isEmpty()) {
                _lastErrorMessage.value = "Handshake failed: server did not provide its public key."
                return@withContext false
            }
            val serverPubDer = Base64.getDecoder().decode(serverPubB64)

            // Send PAIR_REQUEST (first time) or AUTH_RESPONSE (already paired)
            val clientNonce = java.security.SecureRandom.getSeed(32)
            // Salt = serverNonce || clientNonce  (matches server: combined_nonce = server_nonce + client_nonce)
            val combinedNonce = serverNonce + clientNonce

            val pairReq = mapOf(
                "device_id" to deviceId,
                "name" to deviceName,
                "client_pub" to Base64.getEncoder().encodeToString(clientPublicKeyBytes),
                "client_nonce" to Base64.getEncoder().encodeToString(clientNonce),
            )
            sendEncoded(Protocol.MsgType.PAIR_REQUEST, pairReq)

            // Wait for PAIR_CONFIRM or PAIR_REJECT.
            // PAIR_CONFIRM is still protected by the zero key — do NOT set the session key yet.
            val response = readOneFrame(stream)
            if (response == null) {
                _lastErrorMessage.value = "Handshake error: could not decode response frame from ${info.name}."
                return@withContext false
            }
            return@withContext when (response.type) {
                Protocol.MsgType.PAIR_CONFIRM -> {
                    Log.i(TAG, "Pairing confirmed")
                    // Derive session key AFTER decoding PAIR_CONFIRM (which uses the zero key)
                    if (!deriveSessionKey(serverPubDer, combinedNonce)) {
                        return@withContext false
                    }
                    true
                }
                Protocol.MsgType.PAIR_REJECT -> {
                    val reason = response.payload["reason"] as? String ?: "Pairing declined"
                    Log.w(TAG, "Pairing rejected: $reason")
                    _lastErrorMessage.value = "Pairing rejected by ${info.name}: $reason"
                    false
                }
                else -> {
                    Log.e(TAG, "Unexpected response during handshake: 0x${response.type.toString(16)}")
                    _lastErrorMessage.value = "Unexpected response during handshake: 0x${response.type.toString(16)}"
                    false
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Handshake failed: ${e.message}")
            _lastErrorMessage.value = "Handshake failed: ${e.localizedMessage}"
            false
        }
    }

    /**
     * Perform ECDH with the server's public key and derive the 32-byte session key
     * via HKDF-SHA256, matching the server's ecdh_derive_session_key():
     *
     *   shared  = ECDH(clientPrivateKey, serverPublicKey)     // 32-byte x-coordinate
     *   prk     = HMAC-SHA256(key = salt, data = shared)      // extract
     *   T1      = HMAC-SHA256(key = prk,  data = info || 0x01) // expand
     *   sessionKey = T1
     *
     * @param serverPubDer  DER-encoded SubjectPublicKeyInfo bytes from the HELLO frame
     * @param salt          serverNonce || clientNonce (combined nonce)
     * @return true on success; on failure sets _lastErrorMessage and returns false
     */
    private fun deriveSessionKey(serverPubDer: ByteArray, salt: ByteArray): Boolean {
        return try {
            val privKey = clientPrivateKey
                ?: throw IllegalStateException("Client private key not initialised")

            // Reconstruct the server's EC public key from its DER SubjectPublicKeyInfo encoding
            val serverPub = java.security.KeyFactory.getInstance("EC")
                .generatePublic(java.security.spec.X509EncodedKeySpec(serverPubDer))

            // ECDH: obtain the raw shared secret (32 bytes for P-256)
            val ka = javax.crypto.KeyAgreement.getInstance("ECDH")
            ka.init(privKey)
            ka.doPhase(serverPub, true)
            val shared = ka.generateSecret()  // 32-byte x-coordinate (big-endian)

            // HKDF-SHA256(ikm = shared, salt = combinedNonce, info = "aethercontrol-session-v1", length = 32)
            val key = hkdfSha256(
                ikm  = shared,
                salt = salt,
                info = "aethercontrol-session-v1".toByteArray(Charsets.UTF_8),
                length = 32,
            )

            codec.setSessionKey(key)
            Log.d(TAG, "Session key derived via ECDH+HKDF")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Secure channel setup failed: ${e.message}", e)
            _lastErrorMessage.value = "Secure channel setup failed: ${e.localizedMessage ?: e.javaClass.simpleName}"
            false
        }
    }

    /**
     * RFC-5869 HKDF-SHA256 (extract + single expand step for length ≤ 32).
     *
     *   prk = HMAC-SHA256(key = salt, data = ikm)          // extract
     *   T1  = HMAC-SHA256(key = prk,  data = info || 0x01) // expand
     *   return T1[:length]
     */
    internal fun hkdfSha256(
        ikm: ByteArray,
        salt: ByteArray,
        info: ByteArray,
        length: Int = 32,
    ): ByteArray {
        require(length <= 32) { "hkdfSha256: length must be ≤ 32 (single T1 block)" }
        val mac = javax.crypto.Mac.getInstance("HmacSHA256")

        // Extract: PRK = HMAC-SHA256(key=salt, data=ikm)
        mac.init(javax.crypto.spec.SecretKeySpec(salt, "HmacSHA256"))
        val prk = mac.doFinal(ikm)

        // Expand T1 = HMAC-SHA256(key=PRK, data=info || 0x01)
        mac.init(javax.crypto.spec.SecretKeySpec(prk, "HmacSHA256"))
        mac.update(info)
        mac.update(0x01.toByte())
        val t1 = mac.doFinal()

        return if (length == 32) t1 else t1.copyOf(length)
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
        // FIX 2 (Android): track consecutive HMAC decode failures right after connection
        var consecutiveDecodeFailures = 0
        val maxDecodeFailures = 5
        while (running.get()) {
            try {
                val n = stream.read(buf)
                if (n <= 0) break
                frameBuffer.feed(buf.copyOf(n))
                val frames = frameBuffer.getFrames()
                if (frames.isEmpty() && frameBuffer.hadRecentHmacFailure()) {
                    consecutiveDecodeFailures++
                    if (consecutiveDecodeFailures >= maxDecodeFailures) {
                        Log.e(TAG, "$maxDecodeFailures consecutive HMAC failures — secure channel error")
                        _lastErrorMessage.value = "Secure channel error — keys may be mismatched. Please reconnect."
                        _state.value = ConnectionState.ERROR
                        running.set(false)
                        break
                    }
                } else if (frames.isNotEmpty()) {
                    consecutiveDecodeFailures = 0
                }
                frames.forEach { msg ->
                    when (msg.type) {
                        Protocol.MsgType.HEARTBEAT -> sendEncoded(Protocol.MsgType.HEARTBEAT, mapOf("ts" to System.currentTimeMillis()))
                        else -> {
                            _messages.trySend(msg)
                            _messagesFlow.tryEmit(msg)
                        }
                    }
                }
            } catch (e: Exception) {
                if (running.get()) Log.w(TAG, "Receive error: ${e.message}")
                break
            }
        }
        Log.i(TAG, "Receive loop ended")
        if (_state.value != ConnectionState.ERROR) {
            _state.value = ConnectionState.DISCONNECTED
        }
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
