package com.aethercontrol.ui.screens

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Base64
import android.util.Log
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
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
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aethercontrol.network.NetworkManager
import com.aethercontrol.network.Protocol
import com.aethercontrol.ui.theme.AetherColors
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RemoteDesktopScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    var bitmap by remember { mutableStateOf<Bitmap?>(null) }
    var remoteWidth by remember { mutableStateOf(1920) }
    var remoteHeight by remember { mutableStateOf(1080) }
    var selectedQuality by remember { mutableStateOf("medium") }
    var fps by remember { mutableStateOf(0) }
    var frameCounter by remember { mutableStateOf(0) }
    var isConnecting by remember { mutableStateOf(true) }
    var showControls by remember { mutableStateOf(true) }
    var showKeyboard by remember { mutableStateOf(false) }
    var textInput by remember { mutableStateOf("") }
    var containerSize by remember { mutableStateOf(IntSize.Zero) }

    // Measure FPS
    LaunchedEffect(Unit) {
        var lastTime = System.currentTimeMillis()
        while (true) {
            kotlinx.coroutines.delay(1000)
            val now = System.currentTimeMillis()
            val elapsed = (now - lastTime) / 1000f
            if (elapsed > 0) {
                fps = (frameCounter / elapsed).toInt()
                frameCounter = 0
            }
            lastTime = now
        }
    }

    // Request stream & process incoming frames
    LaunchedEffect(selectedQuality) {
        networkManager.requestScreenStream(selectedQuality, 30)
    }

    DisposableEffect(Unit) {
        onDispose { networkManager.stopScreenStream() }
    }

    LaunchedEffect(Unit) {
        networkManager.messagesFlow.collect { msg ->
            if (msg.type == Protocol.MsgType.SCREEN_FRAME) {
                val dataStr = msg.payload["data"] as? String ?: return@collect
                val w = (msg.payload["w"] as? Number)?.toInt() ?: 1920
                val h = (msg.payload["h"] as? Number)?.toInt() ?: 1080
                withContext(Dispatchers.Default) {
                    val decodedBitmap = try {
                        val bytes = Base64.decode(dataStr, Base64.DEFAULT)
                        BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                    } catch (e: Exception) {
                        Log.e("RemoteDesktop", "Frame decode error: ${e.message}")
                        null
                    }
                    if (decodedBitmap != null) {
                        withContext(Dispatchers.Main) {
                            bitmap = decodedBitmap
                            remoteWidth = w
                            remoteHeight = h
                            isConnecting = false
                            frameCounter++
                        }
                    }
                }
            }
        }
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(Color.Black)
            .onGloballyPositioned { containerSize = it.size }
    ) {
        if (bitmap != null) {
            val imgBitmap = bitmap!!.asImageBitmap()

            val scaleX = if (remoteWidth > 0) containerSize.width.toFloat() / remoteWidth else 1f
            val scaleY = if (remoteHeight > 0) containerSize.height.toFloat() / remoteHeight else 1f
            val fitScale = minOf(scaleX, scaleY)

            val renderedW = remoteWidth * fitScale
            val renderedH = remoteHeight * fitScale

            val offsetX = (containerSize.width - renderedW) / 2f
            val offsetY = (containerSize.height - renderedH) / 2f

            Box(
                Modifier
                    .fillMaxSize()
                    .pointerInput(containerSize, remoteWidth, remoteHeight) {
                        detectTapGestures(
                            onTap = { offset ->
                                val relX = offset.x - offsetX
                                val relY = offset.y - offsetY
                                if (relX in 0f..renderedW && relY in 0f..renderedH && renderedW > 0 && renderedH > 0) {
                                    val xRatio = relX / renderedW
                                    val yRatio = relY / renderedH
                                    val targetX = (xRatio * remoteWidth).toInt()
                                    val targetY = (yRatio * remoteHeight).toInt()
                                    networkManager.sendMouseMoveAbs(targetX, targetY, xRatio, yRatio)
                                    networkManager.sendMouseButton(0, true)
                                    networkManager.sendMouseButton(0, false)
                                }
                            },
                            onLongPress = { offset ->
                                val relX = offset.x - offsetX
                                val relY = offset.y - offsetY
                                if (relX in 0f..renderedW && relY in 0f..renderedH && renderedW > 0 && renderedH > 0) {
                                    val xRatio = relX / renderedW
                                    val yRatio = relY / renderedH
                                    val targetX = (xRatio * remoteWidth).toInt()
                                    val targetY = (yRatio * remoteHeight).toInt()
                                    networkManager.sendMouseMoveAbs(targetX, targetY, xRatio, yRatio)
                                    networkManager.sendMouseButton(1, true)
                                    networkManager.sendMouseButton(1, false)
                                }
                            }
                        )
                    }
                    .pointerInput(containerSize, remoteWidth, remoteHeight) {
                        detectDragGestures { change, _ ->
                            change.consume()
                            val relX = change.position.x - offsetX
                            val relY = change.position.y - offsetY
                            if (renderedW > 0 && renderedH > 0) {
                                val xRatio = (relX / renderedW).coerceIn(0f, 1f)
                                val yRatio = (relY / renderedH).coerceIn(0f, 1f)
                                val targetX = (xRatio * remoteWidth).toInt()
                                val targetY = (yRatio * remoteHeight).toInt()
                                networkManager.sendMouseMoveAbs(targetX, targetY, xRatio, yRatio)
                            }
                        }
                    },
                contentAlignment = Alignment.Center
            ) {
                Image(
                    bitmap = imgBitmap,
                    contentDescription = "Remote Desktop Frame",
                    modifier = Modifier.fillMaxSize(),
                    contentScale = ContentScale.Fit
                )
            }
        } else {
            Column(
                modifier = Modifier.align(Alignment.Center),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                CircularProgressIndicator(color = AetherColors.Primary)
                Spacer(Modifier.height(16.dp))
                Text("Connecting to Remote Desktop Stream...", color = AetherColors.TextSecondary, fontSize = 14.sp)
            }
        }

        // Floating Overlay Controls
        if (showControls) {
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
                        IconButton(onClick = { networkManager.sendMouseButton(0, true); networkManager.sendMouseButton(0, false) }) {
                            Icon(Icons.Filled.Mouse, "Left Click", tint = Color.White)
                        }
                        IconButton(onClick = { networkManager.sendMouseButton(1, true); networkManager.sendMouseButton(1, false) }) {
                            Icon(Icons.Filled.TouchApp, "Right Click", tint = AetherColors.PrimaryLight)
                        }
                        IconButton(onClick = { showKeyboard = !showKeyboard }) {
                            Icon(Icons.Filled.Keyboard, "Toggle Keyboard", tint = if (showKeyboard) AetherColors.Primary else Color.White)
                        }
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
        }

        // Soft Keyboard Input Overlay
        if (showKeyboard) {
            val focusRequester = remember { androidx.compose.ui.focus.FocusRequester() }
            LaunchedEffect(showKeyboard) {
                focusRequester.requestFocus()
            }
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
}

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
