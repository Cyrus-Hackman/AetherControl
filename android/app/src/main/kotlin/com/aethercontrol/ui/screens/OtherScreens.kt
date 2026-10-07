package com.aethercontrol.ui.screens

import android.graphics.Bitmap
import android.graphics.SurfaceTexture
import android.media.MediaCodec
import android.media.MediaFormat
import android.util.Base64
import android.util.Log
import android.view.Surface
import android.view.TextureView
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.*
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.aethercontrol.network.NetworkManager
import com.aethercontrol.network.Protocol
import com.aethercontrol.ui.theme.AetherColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

private const val TAG = "RemoteDesktop"
private const val MIME_H264 = "video/avc"

// ─────────────────────────────────────────────────────────────────────────────
// MediaCodec H.264 decoder helper
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Thin wrapper around MediaCodec configured for low-latency H.264 decoding.
 * Output is rendered directly to the provided [Surface] — no Bitmap copies.
 */
class H264Decoder(private val width: Int, private val height: Int, private val surface: Surface) {

    private var codec: MediaCodec? = null
    private var configured = false

    fun start() {
        try {
            val format = MediaFormat.createVideoFormat(MIME_H264, width, height).apply {
                // Low-latency flag (API 30+); ignored gracefully on older devices
                setInteger(MediaFormat.KEY_LOW_LATENCY, 1)
            }
            val mc = MediaCodec.createDecoderByType(MIME_H264)
            mc.configure(format, surface, null, 0)
            mc.start()
            codec = mc
            configured = true
            Log.i(TAG, "MediaCodec H264 decoder started ($width×$height)")
        } catch (e: Exception) {
            Log.e(TAG, "MediaCodec init failed: ${e.message}")
            configured = false
        }
    }

    /**
     * Feed one Annex-B NAL packet to the decoder.
     * The decoded frame is rendered automatically to the Surface.
     */
    fun feedFrame(data: ByteArray, presentationTimeUs: Long, isKeyframe: Boolean) {
        val mc = codec ?: return
        if (!configured) return
        try {
            val inputIdx = mc.dequeueInputBuffer(0)
            if (inputIdx >= 0) {
                val buf = mc.getInputBuffer(inputIdx) ?: return
                buf.clear()
                buf.put(data)
                val flags = if (isKeyframe) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0
                mc.queueInputBuffer(inputIdx, 0, data.size, presentationTimeUs, flags)
            }

            val info = MediaCodec.BufferInfo()
            var outputIdx = mc.dequeueOutputBuffer(info, 0)
            while (outputIdx >= 0) {
                // render=true → frame is pushed to the Surface automatically
                mc.releaseOutputBuffer(outputIdx, true)
                outputIdx = mc.dequeueOutputBuffer(info, 0)
            }
        } catch (e: Exception) {
            Log.w(TAG, "feedFrame error: ${e.message}")
        }
    }

    fun stop() {
        try {
            codec?.stop()
            codec?.release()
        } catch (_: Exception) {}
        codec = null
        configured = false
        Log.i(TAG, "MediaCodec H264 decoder stopped")
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// RemoteDesktopScreen
// ─────────────────────────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RemoteDesktopScreen(networkManager: NetworkManager, onBack: () -> Unit) {

    // ── Display state ──────────────────────────────────────────────────────
    var remoteWidth  by remember { mutableStateOf(1920) }
    var remoteHeight by remember { mutableStateOf(1080) }
    var selectedQuality by remember { mutableStateOf("medium") }
    var fps by remember { mutableStateOf(0) }
    var frameCounter by remember { mutableStateOf(0) }
    var isConnecting  by remember { mutableStateOf(true) }
    var errorMessage  by remember { mutableStateOf<String?>(null) }
    var showKeyboard  by remember { mutableStateOf(false) }
    var textInput     by remember { mutableStateOf("") }
    var containerSize by remember { mutableStateOf(IntSize.Zero) }

    // ── Extended display state ─────────────────────────────────────────────
    var displayMode by remember { mutableStateOf("mirror") }   // "mirror" | "extend"
    var showDisplaySheet by remember { mutableStateOf(false) }

    // ── Surface / decoder state ────────────────────────────────────────────
    var decoderSurface  by remember { mutableStateOf<Surface?>(null) }
    var currentDecoder  by remember { mutableStateOf<H264Decoder?>(null) }
    // Track last known remote dimensions for decoder re-init
    var decoderWidth  by remember { mutableStateOf(0) }
    var decoderHeight by remember { mutableStateOf(0) }

    val context = LocalContext.current

    // ── FPS counter ────────────────────────────────────────────────────────
    LaunchedEffect(Unit) {
        var lastTime = System.currentTimeMillis()
        while (true) {
            delay(1000)
            val now = System.currentTimeMillis()
            val elapsed = (now - lastTime) / 1000f
            if (elapsed > 0) {
                fps = (frameCounter / elapsed).toInt()
                frameCounter = 0
            }
            lastTime = now
        }
    }

    // ── Request stream on quality/mode change ──────────────────────────────
    LaunchedEffect(selectedQuality) {
        networkManager.requestScreenStream(selectedQuality, 30)
    }

    DisposableEffect(Unit) {
        onDispose {
            networkManager.stopScreenStream()
            currentDecoder?.stop()
        }
    }

    // ── Frame collection: H.264 path ──────────────────────────────────────
    LaunchedEffect(Unit) {
        networkManager.messagesFlow.collect { msg ->
            when (msg.type) {
                Protocol.MsgType.SCREEN_FRAME -> {
                    val dataStr = msg.payload["data"] as? String ?: return@collect
                    val w = (msg.payload["w"] as? Number)?.toInt() ?: 1920
                    val h = (msg.payload["h"] as? Number)?.toInt() ?: 1080
                    val isKf = msg.payload["kf"] as? Boolean ?: false
                    val seq  = (msg.payload["seq"] as? Number)?.toLong() ?: 0L
                    val fmt  = msg.payload["fmt"] as? String ?: "h264"

                    withContext(Dispatchers.IO) {
                        try {
                            val bytes = Base64.decode(dataStr, Base64.DEFAULT)

                            if (fmt == "h264") {
                                // ── H.264 / MediaCodec path ───────────────
                                // Re-init decoder if dimensions changed
                                if (w != decoderWidth || h != decoderHeight) {
                                    currentDecoder?.stop()
                                    val surface = decoderSurface
                                    if (surface != null && surface.isValid) {
                                        val dec = H264Decoder(w, h, surface)
                                        dec.start()
                                        currentDecoder = dec
                                        decoderWidth  = w
                                        decoderHeight = h
                                    }
                                }
                                currentDecoder?.feedFrame(bytes, seq * 33_333L, isKf)
                                withContext(Dispatchers.Main) {
                                    remoteWidth  = w
                                    remoteHeight = h
                                    isConnecting = false
                                    errorMessage = null
                                    frameCounter++
                                }
                            } else {
                                // ── Legacy JPEG fallback (server not yet upgraded) ──
                                val bitmap = android.graphics.BitmapFactory
                                    .decodeByteArray(bytes, 0, bytes.size)
                                if (bitmap != null) {
                                    withContext(Dispatchers.Main) {
                                        remoteWidth  = w
                                        remoteHeight = h
                                        isConnecting = false
                                        errorMessage = null
                                        frameCounter++
                                    }
                                }
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "Frame decode error: ${e.message}")
                        }
                    }
                }
                Protocol.MsgType.DISPLAY_MODE_STATE -> {
                    val mode = msg.payload["mode"] as? String ?: "mirror"
                    withContext(Dispatchers.Main) { displayMode = mode }
                }
                Protocol.MsgType.ERROR -> {
                    val errorStr = msg.payload["message"] as? String
                        ?: "Server returned error (code ${msg.payload["code"]})"
                    withContext(Dispatchers.Main) {
                        isConnecting = false
                        errorMessage = errorStr
                    }
                }
            }
        }
    }

    // ── Coordinate helpers (fit-to-container) ─────────────────────────────
    //
    // The surface fills the container and the server sends frames at
    // (remoteWidth × remoteHeight).  We preserve the same coordinate
    // mapping that the old bitmap path used so touch works correctly.
    fun toRemoteCoords(touchX: Float, touchY: Float): Pair<Float, Float>? {
        val cw = containerSize.width.toFloat()
        val ch = containerSize.height.toFloat()
        if (cw <= 0 || ch <= 0 || remoteWidth <= 0 || remoteHeight <= 0) return null
        val scaleX = cw / remoteWidth
        val scaleY = ch / remoteHeight
        val fitScale = minOf(scaleX, scaleY)
        val renderedW = remoteWidth * fitScale
        val renderedH = remoteHeight * fitScale
        val offsetX = (cw - renderedW) / 2f
        val offsetY = (ch - renderedH) / 2f
        val relX = touchX - offsetX
        val relY = touchY - offsetY
        if (relX < 0 || relX > renderedW || relY < 0 || relY > renderedH) return null
        val xRatio = relX / renderedW
        val yRatio = relY / renderedH
        return Pair(xRatio, yRatio)
    }

    // ─────────────────────────────────────────────────────────────────────
    // Root container
    // ─────────────────────────────────────────────────────────────────────
    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .onGloballyPositioned { containerSize = it.size }
    ) {

        // ── TextureView for H.264 output ───────────────────────────────
        AndroidView(
            factory = { ctx ->
                TextureView(ctx).apply {
                    surfaceTextureListener = object : TextureView.SurfaceTextureListener {
                        override fun onSurfaceTextureAvailable(st: SurfaceTexture, w: Int, h: Int) {
                            val surf = Surface(st)
                            decoderSurface = surf
                            // If we already know the dimensions, start the decoder immediately
                            if (remoteWidth > 0 && remoteHeight > 0 && surf.isValid) {
                                val dec = H264Decoder(remoteWidth, remoteHeight, surf)
                                dec.start()
                                currentDecoder = dec
                                decoderWidth  = remoteWidth
                                decoderHeight = remoteHeight
                            }
                        }
                        override fun onSurfaceTextureSizeChanged(st: SurfaceTexture, w: Int, h: Int) {}
                        override fun onSurfaceTextureDestroyed(st: SurfaceTexture): Boolean {
                            currentDecoder?.stop()
                            currentDecoder = null
                            decoderSurface = null
                            return true
                        }
                        override fun onSurfaceTextureUpdated(st: SurfaceTexture) {
                            // Frame rendered to surface — nothing to do here
                        }
                    }
                }
            },
            modifier = Modifier
                .fillMaxSize()
                // ── Gestures ──────────────────────────────────────────
                .pointerInput(containerSize, remoteWidth, remoteHeight) {
                    // Single-finger tap → click; long-press → right-click
                    detectTapGestures(
                        onTap = { offset ->
                            val (xr, yr) = toRemoteCoords(offset.x, offset.y) ?: return@detectTapGestures
                            val tx = (xr * remoteWidth).toInt()
                            val ty = (yr * remoteHeight).toInt()
                            networkManager.sendMouseMoveAbs(tx, ty, xr, yr)
                            networkManager.sendMouseButton(0, true)
                            networkManager.sendMouseButton(0, false)
                        },
                        onLongPress = { offset ->
                            val (xr, yr) = toRemoteCoords(offset.x, offset.y) ?: return@detectTapGestures
                            val tx = (xr * remoteWidth).toInt()
                            val ty = (yr * remoteHeight).toInt()
                            networkManager.sendMouseMoveAbs(tx, ty, xr, yr)
                            networkManager.sendMouseButton(1, true)
                            networkManager.sendMouseButton(1, false)
                        },
                    )
                }
                .pointerInput(containerSize, remoteWidth, remoteHeight) {
                    // Single-finger drag → click-and-drag (press → move → release)
                    // Two-finger scroll / two-finger tap handled in the block below
                    detectDragGestures(
                        onDragStart = { offset ->
                            val (xr, yr) = toRemoteCoords(offset.x, offset.y) ?: return@detectDragGestures
                            val tx = (xr * remoteWidth).toInt()
                            val ty = (yr * remoteHeight).toInt()
                            networkManager.sendMouseMoveAbs(tx, ty, xr, yr)
                            networkManager.sendMouseButton(0, true)   // press on drag start
                        },
                        onDrag = { change, _ ->
                            change.consume()
                            val (xr, yr) = toRemoteCoords(change.position.x, change.position.y)
                                ?: return@detectDragGestures
                            val tx = (xr * remoteWidth).toInt()
                            val ty = (yr * remoteHeight).toInt()
                            networkManager.sendMouseMoveAbs(tx, ty, xr, yr)
                        },
                        onDragEnd = {
                            networkManager.sendMouseButton(0, false)  // release on drag end
                        },
                        onDragCancel = {
                            networkManager.sendMouseButton(0, false)
                        },
                    )
                }
                .pointerInput(containerSize, remoteWidth, remoteHeight) {
                    // Two-finger scroll + two-finger tap (middle click)
                    awaitPointerEventScope {
                        var twoFingerTapCandidate = false

                        while (true) {
                            val event = awaitPointerEvent()
                            val pointers = event.changes.filter { it.pressed }

                            if (pointers.size == 2) {
                                val p0 = pointers[0]
                                val p1 = pointers[1]

                                // Detect a stationary two-finger tap for middle-click
                                val moved0 = (p0.position - p0.previousPosition).getDistance() > 8f
                                val moved1 = (p1.position - p1.previousPosition).getDistance() > 8f
                                if (!moved0 && !moved1) {
                                    twoFingerTapCandidate = true
                                } else {
                                    twoFingerTapCandidate = false
                                    // Compute average scroll delta
                                    val dy0 = p0.position.y - p0.previousPosition.y
                                    val dy1 = p1.position.y - p1.previousPosition.y
                                    val dx0 = p0.position.x - p0.previousPosition.x
                                    val dx1 = p1.position.x - p1.previousPosition.x
                                    val avgDy = ((dy0 + dy1) / 2f)
                                    val avgDx = ((dx0 + dx1) / 2f)
                                    // Throttle: only send if delta is meaningful
                                    if (kotlin.math.abs(avgDy) > 1f || kotlin.math.abs(avgDx) > 1f) {
                                        networkManager.sendMouseScroll(
                                            dx = -(avgDx / 20f).toInt(),
                                            dy =  (avgDy / 20f).toInt(),
                                        )
                                    }
                                }
                                event.changes.forEach { it.consume() }
                            } else if (pointers.isEmpty() && twoFingerTapCandidate) {
                                // All fingers lifted after a stationary two-finger placement = middle click
                                networkManager.sendMouseButton(2, true)   // MIDDLE = index 2
                                networkManager.sendMouseButton(2, false)
                                twoFingerTapCandidate = false
                            } else {
                                twoFingerTapCandidate = false
                            }
                        }
                    }
                }
        )

        // ── Connecting / Error overlays ────────────────────────────────
        if (isConnecting) {
            Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                CircularProgressIndicator(color = AetherColors.Primary)
                Spacer(Modifier.height(16.dp))
                Text("Connecting to Remote Desktop Stream...", color = AetherColors.TextSecondary, fontSize = 14.sp)
            }
        }

        errorMessage?.let { errMsg ->
            Column(
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Icon(
                    imageVector = Icons.Filled.Warning,
                    contentDescription = null,
                    tint = AetherColors.Error,
                    modifier = Modifier.size(48.dp)
                )
                Spacer(Modifier.height(16.dp))
                Text(
                    text = errMsg,
                    color = AetherColors.TextPrimary,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center
                )
                Spacer(Modifier.height(24.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    OutlinedButton(onClick = onBack) {
                        Text("Go Back", color = AetherColors.TextSecondary)
                    }
                    Button(
                        onClick = {
                            errorMessage = null
                            isConnecting = true
                            networkManager.requestScreenStream(selectedQuality, 30)
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = AetherColors.Primary)
                    ) {
                        Text("Retry")
                    }
                }
            }
        }

        // ── Top control bar ────────────────────────────────────────────
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.TopCenter),
            color = Color.Black.copy(alpha = 0.75f),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, "Back", tint = Color.White)
                    }
                    Text(
                        "Remote Desktop",
                        color = Color.White,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.width(8.dp))
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = AetherColors.Primary.copy(alpha = 0.2f)
                    ) {
                        Text(
                            text = "$fps FPS • ${remoteWidth}x${remoteHeight}",
                            color = AetherColors.Primary,
                            fontSize = 10.sp,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            fontWeight = FontWeight.Medium
                        )
                    }
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    // Left click button
                    IconButton(onClick = {
                        networkManager.sendMouseButton(0, true)
                        networkManager.sendMouseButton(0, false)
                    }) {
                        Icon(Icons.Filled.Mouse, "Left Click", tint = Color.White)
                    }
                    // Right click button
                    IconButton(onClick = {
                        networkManager.sendMouseButton(1, true)
                        networkManager.sendMouseButton(1, false)
                    }) {
                        Icon(Icons.Filled.TouchApp, "Right Click", tint = AetherColors.PrimaryLight)
                    }
                    // Keyboard toggle
                    IconButton(onClick = { showKeyboard = !showKeyboard }) {
                        Icon(
                            Icons.Filled.Keyboard,
                            "Toggle Keyboard",
                            tint = if (showKeyboard) AetherColors.Primary else Color.White
                        )
                    }
                    // Extend / mirror display toggle
                    IconButton(onClick = { showDisplaySheet = true }) {
                        Icon(
                            if (displayMode == "extend") Icons.Filled.Tv else Icons.Filled.Cast,
                            "Display Mode",
                            tint = if (displayMode == "extend") AetherColors.Primary else Color.White
                        )
                    }
                    // Quality selector
                    IconButton(onClick = {
                        selectedQuality = when (selectedQuality) {
                            "low" -> "medium"
                            "medium" -> "high"
                            "high" -> "low"
                            else -> "medium"
                        }
                    }) {
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = AetherColors.Surface
                        ) {
                            Text(
                                selectedQuality.uppercase(),
                                color = Color.White,
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }
            }
        }

        // ── Soft Keyboard Overlay ──────────────────────────────────────
        if (showKeyboard) {
            val focusRequester = remember { androidx.compose.ui.focus.FocusRequester() }
            LaunchedEffect(showKeyboard) { focusRequester.requestFocus() }
            Box(
                Modifier
                    .fillMaxWidth()
                    .align(Alignment.BottomCenter)
                    .background(Color.Black.copy(alpha = 0.85f))
                    .padding(8.dp)
            ) {
                Row(
                    Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    androidx.compose.foundation.text.BasicTextField(
                        value = textInput,
                        onValueChange = { newText ->
                            if (newText.length > textInput.length) {
                                val charTyped = newText.last().toString()
                                networkManager.sendText(charTyped)
                            } else if (newText.length < textInput.length) {
                                networkManager.sendKeyDown("BACKSPACE")
                                networkManager.sendKeyUp("BACKSPACE")
                            }
                            textInput = newText
                        },
                        modifier = Modifier
                            .weight(1f)
                            .padding(8.dp)
                            .focusRequester(focusRequester),
                        textStyle = androidx.compose.ui.text.TextStyle(color = Color.White, fontSize = 14.sp),
                        decorationBox = { innerTextField ->
                            Box {
                                if (textInput.isEmpty()) Text("Type to send keyboard input...", color = Color.Gray, fontSize = 14.sp)
                                innerTextField()
                            }
                        }
                    )
                    IconButton(onClick = {
                        networkManager.sendKeyDown("ENTER")
                        networkManager.sendKeyUp("ENTER")
                    }) {
                        Icon(Icons.Filled.Send, "Enter", tint = AetherColors.Primary)
                    }
                }
            }
        }
    }

    // ── Display mode bottom sheet ──────────────────────────────────────────
    if (showDisplaySheet) {
        DisplayModeSheet(
            currentMode = displayMode,
            onDismiss = { showDisplaySheet = false },
            onSelectMirror = {
                networkManager.sendDisplayMode("mirror")
                showDisplaySheet = false
            },
            onSelectExtend = { w, h ->
                networkManager.sendDisplayMode("extend", w, h)
                showDisplaySheet = false
            },
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Display mode bottom sheet (Part C — extend vs mirror)
// ─────────────────────────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DisplayModeSheet(
    currentMode: String,
    onDismiss: () -> Unit,
    onSelectMirror: () -> Unit,
    onSelectExtend: (width: Int, height: Int) -> Unit,
) {
    val context = LocalContext.current

    // Phone's physical screen resolution (used for the extended display dimensions)
    val displayMetrics = context.resources.displayMetrics
    val screenW = displayMetrics.widthPixels
    val screenH = displayMetrics.heightPixels

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        containerColor = AetherColors.Surface,
    ) {
        Column(
            Modifier
                .fillMaxWidth()
                .padding(horizontal = 24.dp, vertical = 8.dp)
                .padding(bottom = 32.dp),
        ) {
            Text(
                "Display Mode",
                color = AetherColors.TextPrimary,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                "Choose how your phone connects to the PC screen.",
                color = AetherColors.TextSecondary,
                fontSize = 13.sp,
            )
            Spacer(Modifier.height(20.dp))

            DisplayModeOption(
                title = "Mirror PC Screen",
                subtitle = "Stream the PC's primary display (default)",
                icon = Icons.Filled.Cast,
                selected = currentMode == "mirror",
                onClick = onSelectMirror,
            )

            Spacer(Modifier.height(12.dp))

            DisplayModeOption(
                title = "Use as Extended Display",
                subtitle = "Create a virtual secondary monitor on the PC (${screenW}×${screenH}) — X11 only",
                icon = Icons.Filled.Tv,
                selected = currentMode == "extend",
                onClick = { onSelectExtend(screenW, screenH) },
            )

            if (currentMode == "extend") {
                Spacer(Modifier.height(12.dp))
                Surface(
                    color = AetherColors.Primary.copy(alpha = 0.1f),
                    shape = RoundedCornerShape(8.dp),
                ) {
                    Text(
                        "✓ Extended display active. Touch coordinates map 1:1 to the virtual monitor.",
                        color = AetherColors.Primary,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(12.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun DisplayModeOption(
    title: String,
    subtitle: String,
    icon: ImageVector,
    selected: Boolean,
    onClick: () -> Unit,
) {
    val borderColor = if (selected) AetherColors.Primary else AetherColors.Border
    val bgColor = if (selected) AetherColors.Primary.copy(alpha = 0.08f) else AetherColors.SurfaceVariant

    Row(
        Modifier
            .fillMaxWidth()
            .background(bgColor, RoundedCornerShape(12.dp))
            .border(1.dp, borderColor, RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            icon,
            null,
            tint = if (selected) AetherColors.Primary else AetherColors.TextSecondary,
            modifier = Modifier.size(28.dp),
        )
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(title, color = AetherColors.TextPrimary, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Text(subtitle, color = AetherColors.TextSecondary, fontSize = 11.sp)
        }
        if (selected) {
            Icon(Icons.Filled.CheckCircle, null, tint = AetherColors.Primary, modifier = Modifier.size(20.dp))
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MediaScreen
// ─────────────────────────────────────────────────────────────────────────────

@Composable
fun MediaScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .background(AetherColors.Background),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, null, tint = AetherColors.TextSecondary)
            }
            Text("Media Remote", color = AetherColors.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        }

        Spacer(Modifier.weight(1f))

        // Media art placeholder
        Box(
            Modifier
                .size(180.dp)
                .background(AetherColors.Surface, RoundedCornerShape(20.dp))
                .border(1.dp, AetherColors.Border, RoundedCornerShape(20.dp)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Filled.MusicNote, null, tint = AetherColors.TextMuted, modifier = Modifier.size(72.dp))
        }

        Spacer(Modifier.height(24.dp))

        Text("Now Playing", color = AetherColors.TextSecondary, fontSize = 12.sp)
        Text("— Nothing playing —", color = AetherColors.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)

        Spacer(Modifier.height(32.dp))

        // Main controls
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 32.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            MediaBtn(Icons.Filled.SkipPrevious, 48.dp, AetherColors.TextSecondary) {
                networkManager.sendMediaCommand(5)  // PREVIOUS
            }
            MediaBtn(Icons.Filled.PlayCircle, 72.dp, AetherColors.Media) {
                networkManager.sendMediaCommand(2)  // PLAY_PAUSE
            }
            MediaBtn(Icons.Filled.SkipNext, 48.dp, AetherColors.TextSecondary) {
                networkManager.sendMediaCommand(4)  // NEXT
            }
        }

        Spacer(Modifier.height(24.dp))

        // Volume controls
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 24.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            MediaBtn(Icons.Filled.VolumeDown, 40.dp, AetherColors.TextSecondary) {
                networkManager.sendMediaCommand(7)  // VOLUME_DOWN
            }
            Box(
                Modifier
                    .weight(1f)
                    .padding(horizontal = 12.dp)
                    .height(4.dp)
                    .background(AetherColors.SurfaceVariant, CircleShape)
            ) {
                Box(
                    Modifier
                        .fillMaxHeight()
                        .fillMaxWidth(0.6f)
                        .background(AetherColors.Primary, CircleShape)
                )
            }
            MediaBtn(Icons.Filled.VolumeUp, 40.dp, AetherColors.TextSecondary) {
                networkManager.sendMediaCommand(6)  // VOLUME_UP
            }
            MediaBtn(Icons.Filled.VolumeOff, 36.dp, AetherColors.TextMuted) {
                networkManager.sendMediaCommand(8)  // MUTE
            }
        }

        Spacer(Modifier.weight(1f))

        // Extra controls
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            for ((icon, action, label) in listOf(
                Triple(Icons.Filled.Stop,         3, "Stop"),
                Triple(Icons.Filled.Shuffle,      -1, "Shuffle"),
                Triple(Icons.Filled.Repeat,       -1, "Repeat"),
            )) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    IconButton(onClick = { if (action >= 0) networkManager.sendMediaCommand(action) }) {
                        Icon(icon, null, tint = AetherColors.TextSecondary, modifier = Modifier.size(28.dp))
                    }
                    Text(label, color = AetherColors.TextMuted, fontSize = 10.sp)
                }
            }
        }
    }
}

@Composable
fun MediaBtn(
    icon: ImageVector,
    size: androidx.compose.ui.unit.Dp,
    color: Color,
    onClick: () -> Unit,
) {
    IconButton(onClick = onClick, modifier = Modifier.size(size + 16.dp)) {
        Icon(icon, null, tint = color, modifier = Modifier.size(size))
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SystemScreen
// ─────────────────────────────────────────────────────────────────────────────

@Composable
fun SystemScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    var showConfirmDialog by remember { mutableStateOf<Pair<String, Int>?>(null) }

    Column(
        Modifier
            .fillMaxSize()
            .background(AetherColors.Background)
            .verticalScroll(rememberScrollState())
    ) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, null, tint = AetherColors.TextSecondary)
            }
            Text("System Controls", color = AetherColors.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        }

        Spacer(Modifier.height(8.dp))

        SectionHeader("  Safe Actions")
        SystemActionBtn("🔒 Lock Screen",    AetherColors.Primary, isDangerous = false) {
            networkManager.sendSystemCommand(0)
        }
        SystemActionBtn("💤 Sleep",           AetherColors.Gamepad, isDangerous = false) {
            networkManager.sendSystemCommand(1)
        }
        SystemActionBtn("🖥 Show Desktop",    AetherColors.PrimaryLight, isDangerous = false) {
            networkManager.sendSystemCommand(7)
        }

        Spacer(Modifier.height(16.dp))
        SectionHeader("  ⚠️ Dangerous Actions")

        SystemActionBtn("🚪 Log Out",    AetherColors.Warning, isDangerous = true) {
            showConfirmDialog = "Log Out" to 6
        }
        SystemActionBtn("🔄 Restart",   AetherColors.Warning, isDangerous = true) {
            showConfirmDialog = "Restart" to 4
        }
        SystemActionBtn("⏻ Shutdown",  AetherColors.Error, isDangerous = true) {
            showConfirmDialog = "Shutdown" to 5
        }
    }

    showConfirmDialog?.let { (label, action) ->
        AlertDialog(
            onDismissRequest = { showConfirmDialog = null },
            containerColor = AetherColors.Surface,
            title = { Text("Confirm $label?", color = AetherColors.TextPrimary) },
            text = { Text("This will $label the computer.", color = AetherColors.TextSecondary) },
            confirmButton = {
                Button(
                    onClick = {
                        networkManager.sendSystemCommand(action)
                        showConfirmDialog = null
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = AetherColors.Error),
                ) { Text("Yes, $label") }
            },
            dismissButton = {
                TextButton(onClick = { showConfirmDialog = null }) {
                    Text("Cancel", color = AetherColors.TextSecondary)
                }
            },
        )
    }
}

@Composable
fun SystemActionBtn(label: String, color: Color, isDangerous: Boolean, onClick: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp)
            .background(
                if (isDangerous) color.copy(0.08f) else AetherColors.Surface,
                RoundedCornerShape(12.dp),
            )
            .border(
                1.dp,
                if (isDangerous) color.copy(0.3f) else AetherColors.Border,
                RoundedCornerShape(12.dp),
            )
            .clickable(onClick = onClick)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = if (isDangerous) color else AetherColors.TextPrimary, fontSize = 15.sp, fontWeight = FontWeight.Medium)
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// FileTransferScreen
// ─────────────────────────────────────────────────────────────────────────────

@Composable
fun FileTransferScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .background(AetherColors.Background),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, null, tint = AetherColors.TextSecondary)
            }
            Text("File Transfer", color = AetherColors.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        }

        Spacer(Modifier.weight(1f))
        Icon(Icons.Filled.Folder, null, tint = AetherColors.TextMuted, modifier = Modifier.size(80.dp))
        Spacer(Modifier.height(16.dp))
        Text("File Transfer", color = AetherColors.TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text(
            "Send files between your phone and PC.\nStage 7 — full UI coming soon.",
            color = AetherColors.TextSecondary,
            fontSize = 13.sp,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
        Spacer(Modifier.weight(1f))
    }
}
