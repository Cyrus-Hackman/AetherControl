package com.aethercontrol.ui.screens

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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aethercontrol.network.NetworkManager
import com.aethercontrol.ui.theme.AetherColors
import kotlin.math.*

/**
 * Gamepad Screen
 *
 * Provides a full virtual gamepad with:
 * - D-Pad (left side)
 * - Analog left stick (tracks finger position from center)
 * - Face buttons A/B/X/Y (right side)
 * - Shoulder buttons LB/RB/LT/RT
 * - Start/Select/Guide
 *
 * Analog sticks use relative touch tracking from the initial press point,
 * not fixed position (feels like a real controller).
 */
@Composable
fun GamepadScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    Box(
        Modifier
            .fillMaxSize()
            .background(AetherColors.Background)
    ) {
        // Top bar
        Row(Modifier.fillMaxWidth().padding(start = 8.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, null, tint = AetherColors.TextSecondary)
            }
            Text("Gamepad", color = AetherColors.TextPrimary, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
        }

        // Shoulder buttons row
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 8.dp).padding(top = 56.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                ShoulderBtn("LT", AetherColors.Gamepad) { networkManager.sendGamepadButton(6, it) }
                ShoulderBtn("LB", AetherColors.Gamepad) { networkManager.sendGamepadButton(4, it) }
            }
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                SmallBtn("SEL") { networkManager.sendGamepadButton(8, it) }
                SmallBtn("⊕") { networkManager.sendGamepadButton(10, it) }
                SmallBtn("STA") { networkManager.sendGamepadButton(9, it) }
            }
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                ShoulderBtn("RT", AetherColors.Gamepad) { networkManager.sendGamepadButton(7, it) }
                ShoulderBtn("RB", AetherColors.Gamepad) { networkManager.sendGamepadButton(5, it) }
            }
        }

        // Main control area
        Row(
            Modifier.fillMaxSize().padding(top = 120.dp, bottom = 8.dp, start = 8.dp, end = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Left side: D-Pad + Left Stick
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                DPad(networkManager)
                AnalogStick(
                    label = "L",
                    axisX = 0,
                    axisY = 1,
                    buttonId = 11,
                    networkManager = networkManager,
                )
            }

            // Right side: Face buttons + Right Stick
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                FaceButtons(networkManager)
                AnalogStick(
                    label = "R",
                    axisX = 2,
                    axisY = 3,
                    buttonId = 12,
                    networkManager = networkManager,
                )
            }
        }
    }
}

@Composable
fun AnalogStick(label: String, axisX: Int, axisY: Int, buttonId: Int, networkManager: NetworkManager) {
    val stickRadius = 60.dp
    var thumbOffset by remember { mutableStateOf(Offset.Zero) }
    val maxRadius = 50f

    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier.size(stickRadius * 2),
    ) {
        // Background circle
        Box(
            Modifier
                .size(stickRadius * 2)
                .background(AetherColors.SurfaceVariant, CircleShape)
                .border(2.dp, AetherColors.Border, CircleShape)
        )

        // Thumb
        Box(
            Modifier
                .offset(
                    x = (thumbOffset.x / maxRadius * 50).dp,
                    y = (thumbOffset.y / maxRadius * 50).dp,
                )
                .size(48.dp)
                .background(AetherColors.Gamepad, CircleShape)
                .border(2.dp, AetherColors.Gamepad.copy(0.6f), CircleShape)
                .pointerInput(Unit) {
                    awaitEachGesture {
                        val down = awaitFirstDown()
                        networkManager.sendGamepadButton(buttonId, true)
                        var origin = down.position
                        do {
                            val event = awaitPointerEvent()
                            val pointer = event.changes.firstOrNull() ?: break
                            val delta = pointer.position - origin
                            val clamped = Offset(
                                delta.x.coerceIn(-maxRadius, maxRadius),
                                delta.y.coerceIn(-maxRadius, maxRadius),
                            )
                            thumbOffset = clamped
                            networkManager.sendGamepadAxis(axisX, clamped.x / maxRadius)
                            networkManager.sendGamepadAxis(axisY, clamped.y / maxRadius)
                            pointer.consume()
                        } while (event.changes.any { it.pressed })
                        // Release
                        thumbOffset = Offset.Zero
                        networkManager.sendGamepadAxis(axisX, 0f)
                        networkManager.sendGamepadAxis(axisY, 0f)
                        networkManager.sendGamepadButton(buttonId, false)
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            Text(label, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
fun DPad(networkManager: NetworkManager) {
    val dSize = 36.dp
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        DPadBtn("▲", dSize) {
            networkManager.sendGamepadButton(13, it)
        }
        Row {
            DPadBtn("◀", dSize) {
                networkManager.sendGamepadButton(15, it)
            }
            Spacer(Modifier.size(dSize))
            DPadBtn("▶", dSize) {
                networkManager.sendGamepadButton(16, it)
            }
        }
        DPadBtn("▼", dSize) {
            networkManager.sendGamepadButton(14, it)
        }
    }
}

@Composable
fun DPadBtn(label: String, size: androidx.compose.ui.unit.Dp, onPress: (Boolean) -> Unit) {
    var pressed by remember { mutableStateOf(false) }
    Box(
        Modifier
            .size(size)
            .background(
                if (pressed) AetherColors.SurfaceVariant else AetherColors.Surface,
                RoundedCornerShape(4.dp),
            )
            .border(1.dp, AetherColors.Border, RoundedCornerShape(4.dp))
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    pressed = true
                    onPress(true)
                    tryAwaitRelease()
                    pressed = false
                    onPress(false)
                })
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = AetherColors.TextPrimary, fontSize = 16.sp)
    }
}

@Composable
fun FaceButtons(networkManager: NetworkManager) {
    val faceSize = 52.dp
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        FaceBtn("Y", AetherColors.Warning, faceSize) { networkManager.sendGamepadButton(3, it) }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            FaceBtn("X", Color(0xFF4FC3F7), faceSize) { networkManager.sendGamepadButton(2, it) }
            Spacer(Modifier.size(faceSize))
            FaceBtn("B", AetherColors.Error, faceSize) { networkManager.sendGamepadButton(1, it) }
        }
        FaceBtn("A", AetherColors.Success, faceSize) { networkManager.sendGamepadButton(0, it) }
    }
}

@Composable
fun FaceBtn(label: String, color: Color, size: androidx.compose.ui.unit.Dp, onPress: (Boolean) -> Unit) {
    var pressed by remember { mutableStateOf(false) }
    Box(
        Modifier
            .size(size)
            .background(
                if (pressed) color.copy(0.6f) else color.copy(0.2f),
                CircleShape,
            )
            .border(2.dp, color.copy(0.7f), CircleShape)
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    pressed = true
                    onPress(true)
                    tryAwaitRelease()
                    pressed = false
                    onPress(false)
                })
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = color, fontSize = 16.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun ShoulderBtn(label: String, color: Color, onPress: (Boolean) -> Unit) {
    var pressed by remember { mutableStateOf(false) }
    Box(
        Modifier
            .width(72.dp)
            .height(32.dp)
            .background(
                if (pressed) color.copy(0.5f) else color.copy(0.15f),
                RoundedCornerShape(8.dp),
            )
            .border(1.dp, color.copy(0.4f), RoundedCornerShape(8.dp))
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    pressed = true
                    onPress(true)
                    tryAwaitRelease()
                    pressed = false
                    onPress(false)
                })
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = color, fontSize = 13.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
fun SmallBtn(label: String, onPress: (Boolean) -> Unit) {
    var pressed by remember { mutableStateOf(false) }
    Box(
        Modifier
            .size(40.dp)
            .background(
                if (pressed) AetherColors.SurfaceVariant else AetherColors.Surface,
                CircleShape,
            )
            .border(1.dp, AetherColors.Border, CircleShape)
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    pressed = true
                    onPress(true)
                    tryAwaitRelease()
                    pressed = false
                    onPress(false)
                })
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = AetherColors.TextSecondary, fontSize = 10.sp)
    }
}
