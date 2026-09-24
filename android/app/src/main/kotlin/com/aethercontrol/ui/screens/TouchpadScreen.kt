package com.aethercontrol.ui.screens

import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aethercontrol.network.NetworkManager
import com.aethercontrol.ui.theme.AetherColors
import kotlin.math.abs

/**
 * Touchpad Screen
 *
 * Full-screen gesture surface that translates Android touch gestures
 * into protocol mouse events:
 *   - Single finger drag → MOUSE_MOVE
 *   - Tap → left click
 *   - Two-finger tap → right click
 *   - Two-finger scroll → MOUSE_SCROLL
 *   - Long press → drag mode
 */
@Composable
fun TouchpadScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    var lastOffset by remember { mutableStateOf(Offset.Zero) }
    var isScrolling by remember { mutableStateOf(false) }
    var fingerCount by remember { mutableStateOf(0) }
    var tapDetected by remember { mutableStateOf(false) }
    var isDragging by remember { mutableStateOf(false) }

    val sensitivity = 1.8f  // Configurable
    val scrollSensitivity = 0.3f

    Box(
        Modifier
            .fillMaxSize()
            .background(AetherColors.Background)
    ) {
        // Top bar
        Row(
            Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, null, tint = AetherColors.TextSecondary)
            }
            Text(
                "Touchpad",
                color = AetherColors.TextPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            Icon(Icons.Filled.TouchApp, null, tint = AetherColors.Touchpad)
        }

        // Touchpad surface
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(top = 64.dp, bottom = 100.dp, start = 16.dp, end = 16.dp)
                .background(AetherColors.Surface, RoundedCornerShape(16.dp))
                .border(1.dp, AetherColors.Border, RoundedCornerShape(16.dp))
                .pointerInput(Unit) {
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        lastOffset = down.position
                        fingerCount = 1

                        var hasMoved = false
                        do {
                            val event = awaitPointerEvent()
                            val pointers = event.changes.filter { it.pressed }
                            fingerCount = pointers.size

                            if (pointers.size == 1) {
                                val current = pointers[0].position
                                val dx = current.x - lastOffset.x
                                val dy = current.y - lastOffset.y

                                if (abs(dx) > 2 || abs(dy) > 2) {
                                    hasMoved = true
                                    networkManager.sendMouseMove(
                                        (dx * sensitivity).toInt(),
                                        (dy * sensitivity).toInt(),
                                    )
                                    lastOffset = current
                                }
                            } else if (pointers.size == 2) {
                                // Two-finger scroll
                                val p1 = pointers[0].position
                                val p2 = pointers[1].position
                                val centerY = (p1.y + p2.y) / 2
                                val dy = centerY - lastOffset.y
                                if (abs(dy) > 3) {
                                    networkManager.sendMouseScroll(0, (dy * scrollSensitivity).toInt())
                                    lastOffset = Offset((p1.x + p2.x) / 2, centerY)
                                    hasMoved = true
                                }
                            }
                            pointers.forEach { it.consume() }
                        } while (event.changes.any { it.pressed })

                        // Tap detection (no significant movement)
                        if (!hasMoved) {
                            if (fingerCount >= 2) {
                                // Two-finger tap = right click
                                networkManager.sendMouseButton(1, true)
                                networkManager.sendMouseButton(1, false)
                            } else {
                                // Single tap = left click
                                networkManager.sendMouseButton(0, true)
                                networkManager.sendMouseButton(0, false)
                            }
                        }
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            Text(
                "Touch here to control",
                color = AetherColors.TextMuted,
                fontSize = 14.sp,
            )
        }

        // Bottom mouse buttons
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.BottomCenter)
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            MouseButton(
                label = "Left Click",
                modifier = Modifier.weight(2f),
                color = AetherColors.Primary,
                onDown = { networkManager.sendMouseButton(0, true) },
                onUp = { networkManager.sendMouseButton(0, false) },
            )
            MouseButton(
                label = "Middle",
                modifier = Modifier.weight(1f),
                color = AetherColors.SurfaceVariant,
                onDown = { networkManager.sendMouseButton(2, true) },
                onUp = { networkManager.sendMouseButton(2, false) },
            )
            MouseButton(
                label = "Right Click",
                modifier = Modifier.weight(2f),
                color = AetherColors.SurfaceVariant,
                onDown = { networkManager.sendMouseButton(1, true) },
                onUp = { networkManager.sendMouseButton(1, false) },
            )
        }
    }
}

@Composable
fun MouseButton(
    label: String,
    modifier: Modifier = Modifier,
    color: Color,
    onDown: () -> Unit,
    onUp: () -> Unit,
) {
    var pressed by remember { mutableStateOf(false) }
    Box(
        modifier = modifier
            .height(56.dp)
            .background(
                if (pressed) color.copy(alpha = 0.5f) else color.copy(alpha = 0.2f),
                RoundedCornerShape(10.dp)
            )
            .border(1.dp, color.copy(alpha = 0.4f), RoundedCornerShape(10.dp))
            .pointerInput(Unit) {
                detectTapGestures(
                    onPress = {
                        pressed = true
                        onDown()
                        tryAwaitRelease()
                        pressed = false
                        onUp()
                    }
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = color, fontSize = 12.sp, fontWeight = FontWeight.Medium)
    }
}
