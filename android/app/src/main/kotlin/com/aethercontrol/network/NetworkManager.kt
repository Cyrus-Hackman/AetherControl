package com.aethercontrol.network

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

private const val TAG = "NetworkManager"

/**
 * NetworkManager — single source of truth for network state.
 * Used as a shared ViewModel across all screens.
 */
class NetworkManager : ViewModel() {

    private val discovery = DiscoveryClient(viewModelScope)

    val discoveredComputers: StateFlow<List<ComputerInfo>> = discovery.discovered

    private var _currentConnection: Connection? = null
    val currentConnection: Connection? get() = _currentConnection

    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState

    private val _connectedComputer = MutableStateFlow<ComputerInfo?>(null)
    val connectedComputer: StateFlow<ComputerInfo?> = _connectedComputer

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage

    // Static device ID (should be persisted in DataStore in a full implementation)
    val deviceId: String = java.util.UUID.randomUUID().toString()
    val deviceName: String = android.os.Build.MODEL

    init {
        startDiscovery()
    }

    // ── Discovery ─────────────────────────────────────────────────────────

    fun startDiscovery() {
        discovery.startDiscovery()
    }

    fun stopDiscovery() {
        discovery.stopDiscovery()
    }

    // ── Connection ────────────────────────────────────────────────────────

    fun connectTo(computer: ComputerInfo) {
        viewModelScope.launch {
            _connectionState.value = ConnectionState.CONNECTING
            _errorMessage.value = null
            val conn = Connection(
                info = computer,
                deviceId = deviceId,
                deviceName = deviceName,
                scope = viewModelScope,
            )
            _currentConnection = conn
            val success = conn.connect()
            if (success) {
                _connectedComputer.value = computer
                conn.state.collect { state ->
                    _connectionState.value = state
                }
            } else {
                _errorMessage.value = conn.lastErrorMessage.value ?: "Could not connect to ${computer.name}. Check that AetherControl is running on the PC and both devices are on the same network."
                _connectionState.value = ConnectionState.ERROR
                _currentConnection = null
            }
        }
    }

    fun disconnect() {
        _currentConnection?.disconnect()
        _currentConnection = null
        _connectedComputer.value = null
        _errorMessage.value = null
        _connectionState.value = ConnectionState.DISCONNECTED
    }

    // ── Sending shortcuts ─────────────────────────────────────────────────

    fun send(type: Short, payload: Map<String, Any?>) {
        _currentConnection?.send(type, payload) ?: Log.w(TAG, "Send called without connection")
    }

    fun sendMouseMove(dx: Int, dy: Int) = send(
        Protocol.MsgType.MOUSE_MOVE, mapOf("dx" to dx, "dy" to dy)
    )

    fun sendMouseButton(button: Int, pressed: Boolean) = send(
        Protocol.MsgType.MOUSE_BUTTON, mapOf("button" to button, "pressed" to pressed)
    )

    fun sendMouseScroll(dx: Int, dy: Int) = send(
        Protocol.MsgType.MOUSE_SCROLL, mapOf("dx" to dx, "dy" to dy)
    )

    fun sendKeyDown(key: String) = send(Protocol.MsgType.KEY_DOWN, mapOf("key" to key))
    fun sendKeyUp(key: String)   = send(Protocol.MsgType.KEY_UP,   mapOf("key" to key))
    fun sendText(text: String)   = send(Protocol.MsgType.TEXT_INPUT, mapOf("text" to text))

    fun sendGamepadAxis(axis: Int, value: Float) = send(
        Protocol.MsgType.GAMEPAD_AXIS, mapOf("axis" to axis, "value" to value)
    )

    fun sendGamepadButton(button: Int, pressed: Boolean) = send(
        Protocol.MsgType.GAMEPAD_BUTTON, mapOf("button" to button, "pressed" to pressed)
    )

    fun sendMediaCommand(action: Int, extra: Map<String, Any?> = emptyMap()) = send(
        Protocol.MsgType.MEDIA_COMMAND, mapOf("action" to action) + extra
    )

    fun sendSystemCommand(action: Int, extra: Map<String, Any?> = emptyMap()) = send(
        Protocol.MsgType.SYSTEM_COMMAND, mapOf("action" to action) + extra
    )

    fun sendMouseMoveAbs(x: Int, y: Int, xRatio: Float? = null, yRatio: Float? = null) {
        val payload = mutableMapOf<String, Any?>("x" to x, "y" to y)
        if (xRatio != null) payload["x_ratio"] = xRatio
        if (yRatio != null) payload["y_ratio"] = yRatio
        send(Protocol.MsgType.MOUSE_MOVE_ABS, payload)
    }

    val messagesFlow: Flow<AetherMessage> = connectionState
        .flatMapLatest { state ->
            if (state == ConnectionState.CONNECTED) {
                _currentConnection?.messagesFlow ?: emptyFlow()
            } else {
                emptyFlow()
            }
        }

    fun requestScreenStream(quality: String = "medium", fps: Int = 30) = send(
        Protocol.MsgType.SCREEN_START, mapOf("quality" to quality, "fps" to fps)
    )

    fun stopScreenStream() = send(Protocol.MsgType.SCREEN_STOP, mapOf("reason" to "user"))

    override fun onCleared() {
        super.onCleared()
        discovery.stopDiscovery()
        _currentConnection?.disconnect()
    }
}
