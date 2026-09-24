package com.aethercontrol.network

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import org.msgpack.core.MessagePack
import java.net.*
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * AetherControl Protocol Constants (mirrors Python server)
 */
object Protocol {
    const val VERSION: Byte = 1
    val MAGIC = "AETH".toByteArray()
    const val HEADER_SIZE = 15   // magic(4) + version(1) + type(2) + seq(4) + payload_len(4)
    const val HMAC_SIZE = 32

    object MsgType {
        const val HELLO: Short          = 0x01
        const val AUTH_CHALLENGE: Short = 0x02
        const val AUTH_RESPONSE: Short  = 0x03
        const val PAIR_REQUEST: Short   = 0x04
        const val PAIR_CONFIRM: Short   = 0x05
        const val PAIR_REJECT: Short    = 0x06
        const val CAPABILITIES: Short   = 0x07
        const val HEARTBEAT: Short      = 0x08
        const val DISCONNECT: Short     = 0x09
        const val ERROR: Short          = 0x0A

        const val MOUSE_MOVE: Short     = 0x10
        const val MOUSE_BUTTON: Short   = 0x11
        const val MOUSE_SCROLL: Short   = 0x12
        const val MOUSE_MOVE_ABS: Short = 0x13

        const val KEY_DOWN: Short       = 0x20
        const val KEY_UP: Short         = 0x21
        const val TEXT_INPUT: Short     = 0x22

        const val GAMEPAD_AXIS: Short   = 0x30
        const val GAMEPAD_BUTTON: Short = 0x31
        const val GAMEPAD_RUMBLE: Short = 0x32

        const val SENSOR_DATA: Short    = 0x40

        const val SCREEN_START: Short   = 0x50
        const val SCREEN_STOP: Short    = 0x51
        const val SCREEN_FRAME: Short   = 0x52
        const val SCREEN_CONFIG: Short  = 0x53
        const val SCREEN_ACK: Short     = 0x54

        const val MEDIA_COMMAND: Short  = 0x70
        const val MEDIA_STATE: Short    = 0x71

        const val CLIPBOARD_SET: Short  = 0x80
        const val CLIPBOARD_GET: Short  = 0x81
        const val CLIPBOARD_DATA: Short = 0x82

        const val FILE_START: Short     = 0x90
        const val FILE_CHUNK: Short     = 0x91
        const val FILE_END: Short       = 0x92
        const val FILE_ACK: Short       = 0x93
        const val FILE_CANCEL: Short    = 0x94

        const val SYSTEM_COMMAND: Short = 0xA0
        const val APP_LAUNCH: Short     = 0xA1
    }

    object ErrorCode {
        const val UNKNOWN = 0
        const val AUTH_FAILED = 1
        const val NOT_PAIRED = 2
        const val PERMISSION_DENIED = 4
    }
}

/**
 * A decoded incoming message
 */
data class AetherMessage(
    val type: Short,
    val seq: Int,
    val payload: Map<String, Any?>
)

/**
 * Wire codec: encode/decode AetherControl protocol frames.
 * Mirrors the Python Codec class.
 */
class AetherCodec {
    private var sessionKey = ByteArray(32)  // all zeros until authenticated
    private var sequence = 0

    fun setSessionKey(key: ByteArray) {
        require(key.size >= 32) { "Session key must be at least 32 bytes" }
        sessionKey = key.copyOf(32)
    }

    @Synchronized
    fun encode(type: Short, payload: Map<String, Any?>): ByteArray {
        val rawPayload = MessagePack.newDefaultBufferPacker().use { packer ->
            packMap(packer, payload)
            packer.toByteArray()
        }
        val seq = ++sequence

        val header = ByteArray(Protocol.HEADER_SIZE).also { h ->
            Protocol.MAGIC.copyInto(h, 0)
            h[4] = Protocol.VERSION
            h[5] = (type.toInt() shr 8).toByte()
            h[6] = type.toByte()
            h[7] = (seq shr 24).toByte()
            h[8] = (seq shr 16).toByte()
            h[9] = (seq shr 8).toByte()
            h[10] = seq.toByte()
            val payLen = rawPayload.size
            h[11] = (payLen shr 24).toByte()
            h[12] = (payLen shr 16).toByte()
            h[13] = (payLen shr 8).toByte()
            h[14] = payLen.toByte()
        }

        val mac = hmacSha256(sessionKey, header + rawPayload)
        return header + rawPayload + mac
    }

    fun decode(data: ByteArray): AetherMessage? {
        if (data.size < Protocol.HEADER_SIZE + Protocol.HMAC_SIZE) return null
        if (!data.slice(0..3).toByteArray().contentEquals(Protocol.MAGIC)) return null
        // version check
        val version = data[4]
        val typeHigh = data[5].toInt() and 0xFF
        val typeLow = data[6].toInt() and 0xFF
        val msgType = ((typeHigh shl 8) or typeLow).toShort()
        val seq = ((data[7].toInt() and 0xFF) shl 24) or
                  ((data[8].toInt() and 0xFF) shl 16) or
                  ((data[9].toInt() and 0xFF) shl 8) or
                  (data[10].toInt() and 0xFF)
        val payloadLen = ((data[11].toInt() and 0xFF) shl 24) or
                         ((data[12].toInt() and 0xFF) shl 16) or
                         ((data[13].toInt() and 0xFF) shl 8) or
                         (data[14].toInt() and 0xFF)

        val expectedTotal = Protocol.HEADER_SIZE + payloadLen + Protocol.HMAC_SIZE
        if (data.size != expectedTotal) return null

        val rawPayload = data.slice(Protocol.HEADER_SIZE until Protocol.HEADER_SIZE + payloadLen).toByteArray()
        val receivedMac = data.slice(Protocol.HEADER_SIZE + payloadLen until data.size).toByteArray()
        val header = data.slice(0 until Protocol.HEADER_SIZE).toByteArray()
        val expectedMac = hmacSha256(sessionKey, header + rawPayload)

        if (!MessageDigest.isEqual(receivedMac, expectedMac)) {
            Log.w("AetherCodec", "HMAC mismatch — dropping frame")
            return null
        }

        @Suppress("UNCHECKED_CAST")
        val payload = try {
            val unpacker = MessagePack.newDefaultUnpacker(rawPayload)
            unpackValue(unpacker) as? Map<String, Any?> ?: emptyMap()
        } catch (e: Exception) {
            emptyMap<String, Any?>()
        }

        return AetherMessage(msgType, seq, payload)
    }

    private fun hmacSha256(key: ByteArray, data: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(data)
    }

    private fun packMap(packer: org.msgpack.core.MessageBufferPacker, map: Map<String, Any?>) {
        packer.packMapHeader(map.size)
        for ((k, v) in map) {
            packer.packString(k)
            packValue(packer, v)
        }
    }

    private fun packValue(packer: org.msgpack.core.MessageBufferPacker, value: Any?) {
        when (value) {
            null -> packer.packNil()
            is Boolean -> packer.packBoolean(value)
            is Int -> packer.packInt(value)
            is Long -> packer.packLong(value)
            is Float -> packer.packFloat(value)
            is Double -> packer.packDouble(value)
            is String -> packer.packString(value)
            is ByteArray -> { packer.packBinaryHeader(value.size); packer.writePayload(value) }
            is Map<*, *> -> {
                @Suppress("UNCHECKED_CAST")
                val m = value as Map<String, Any?>
                packMap(packer, m)
            }
            is List<*> -> {
                packer.packArrayHeader(value.size)
                value.forEach { packValue(packer, it) }
            }
            else -> packer.packString(value.toString())
        }
    }

    private fun unpackValue(unpacker: org.msgpack.core.MessageUnpacker): Any? {
        val format = unpacker.nextFormat
        return when (format.valueType) {
            org.msgpack.value.ValueType.NIL -> { unpacker.unpackNil(); null }
            org.msgpack.value.ValueType.BOOLEAN -> unpacker.unpackBoolean()
            org.msgpack.value.ValueType.INTEGER -> unpacker.unpackLong()
            org.msgpack.value.ValueType.FLOAT -> unpacker.unpackDouble()
            org.msgpack.value.ValueType.STRING -> unpacker.unpackString()
            org.msgpack.value.ValueType.BINARY -> {
                val len = unpacker.unpackBinaryHeader()
                unpacker.readPayload(len)
            }
            org.msgpack.value.ValueType.MAP -> {
                val size = unpacker.unpackMapHeader()
                val map = mutableMapOf<String, Any?>()
                repeat(size) {
                    val key = unpacker.unpackString()
                    map[key] = unpackValue(unpacker)
                }
                map
            }
            org.msgpack.value.ValueType.ARRAY -> {
                val size = unpacker.unpackArrayHeader()
                (0 until size).map { unpackValue(unpacker) }
            }
            else -> null
        }
    }
}

/**
 * Frame buffer for TCP stream reassembly
 */
class FrameBuffer(private val codec: AetherCodec) {
    private val buffer = java.io.ByteArrayOutputStream()

    fun feed(data: ByteArray) {
        buffer.write(data)
    }

    fun getFrames(): List<AetherMessage> {
        val frames = mutableListOf<AetherMessage>()
        val bytes = buffer.toByteArray()
        buffer.reset()
        var pos = 0

        while (pos < bytes.size) {
            if (pos + Protocol.HEADER_SIZE > bytes.size) {
                buffer.write(bytes, pos, bytes.size - pos)
                break
            }
            // Check magic
            if (bytes[pos] != 'A'.code.toByte() ||
                bytes[pos+1] != 'E'.code.toByte() ||
                bytes[pos+2] != 'T'.code.toByte() ||
                bytes[pos+3] != 'H'.code.toByte()) {
                pos++
                continue
            }
            val payloadLen = ((bytes[pos+11].toInt() and 0xFF) shl 24) or
                             ((bytes[pos+12].toInt() and 0xFF) shl 16) or
                             ((bytes[pos+13].toInt() and 0xFF) shl 8) or
                             (bytes[pos+14].toInt() and 0xFF)
            val total = Protocol.HEADER_SIZE + payloadLen + Protocol.HMAC_SIZE
            if (pos + total > bytes.size) {
                buffer.write(bytes, pos, bytes.size - pos)
                break
            }
            val frame = bytes.slice(pos until pos + total).toByteArray()
            codec.decode(frame)?.let { frames.add(it) }
            pos += total
        }
        return frames
    }
}
