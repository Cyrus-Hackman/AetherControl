package com.aethercontrol.ui.screens

import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aethercontrol.network.NetworkManager
import com.aethercontrol.ui.theme.AetherColors

@Composable
fun KeyboardScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    var shiftActive by remember { mutableStateOf(false) }
    var ctrlActive by remember { mutableStateOf(false) }
    var altActive by remember { mutableStateOf(false) }
    var superActive by remember { mutableStateOf(false) }

    val modifiers = buildList {
        if (shiftActive) add("LSHIFT")
        if (ctrlActive) add("LCTRL")
        if (altActive) add("LALT")
        if (superActive) add("LMETA")
    }

    fun pressKey(key: String) {
        modifiers.forEach { networkManager.sendKeyDown(it) }
        networkManager.sendKeyDown(key)
        networkManager.sendKeyUp(key)
        modifiers.forEach { networkManager.sendKeyUp(it) }
        // Auto-release shift after key press
        if (shiftActive) shiftActive = false
    }

    Column(
        Modifier
            .fillMaxSize()
            .background(AetherColors.Background)
    ) {
        // Top bar
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, null, tint = AetherColors.TextSecondary)
            }
            Text(
                "Keyboard",
                color = AetherColors.TextPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }

        // Modifier status row
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            ModKey("CTRL",  ctrlActive)  { ctrlActive = !ctrlActive }
            ModKey("ALT",   altActive)   { altActive = !altActive }
            ModKey("SHIFT", shiftActive) { shiftActive = !shiftActive }
            ModKey("⊞",     superActive) { superActive = !superActive }
        }

        Spacer(Modifier.height(12.dp))

        // Function row
        KeyRow(
            keys = listOf("ESC", "F1", "F2", "F3", "F4", "F5", "F6"),
            onPress = ::pressKey,
            specialColor = AetherColors.Error.copy(0.3f),
        )
        KeyRow(
            keys = listOf("F7", "F8", "F9", "F10", "F11", "F12", "PRINTSCREEN"),
            onPress = ::pressKey,
            specialColor = AetherColors.Error.copy(0.3f),
        )

        Spacer(Modifier.height(6.dp))

        // QWERTY row 1
        KeyRow(keys = listOf("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"), onPress = ::pressKey)
        KeyRow(keys = listOf("a", "s", "d", "f", "g", "h", "j", "k", "l"), onPress = ::pressKey)
        KeyRow(keys = listOf("z", "x", "c", "v", "b", "n", "m"), onPress = ::pressKey)

        Spacer(Modifier.height(6.dp))

        // Navigation row
        KeyRow(
            keys = listOf("HOME", "END", "UP", "PAGEUP", "INSERT"),
            onPress = ::pressKey,
            specialColor = AetherColors.Gamepad.copy(0.3f),
        )
        KeyRow(
            keys = listOf("DEL", "LEFT", "DOWN", "RIGHT", "PAGEDOWN"),
            onPress = ::pressKey,
            specialColor = AetherColors.Gamepad.copy(0.3f),
        )

        Spacer(Modifier.height(6.dp))

        // Bottom row
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            KeyButton(
                label = "TAB",
                modifier = Modifier.weight(1.2f),
                color = AetherColors.SurfaceVariant,
                onPress = { pressKey("TAB") },
            )
            KeyButton(
                label = "SPACE",
                modifier = Modifier.weight(3f),
                color = AetherColors.SurfaceVariant,
                onPress = { pressKey("SPACE") },
            )
            KeyButton(
                label = "⌫",
                modifier = Modifier.weight(1.2f),
                color = AetherColors.Error.copy(0.3f),
                onPress = { pressKey("BACKSPACE") },
            )
            KeyButton(
                label = "↵",
                modifier = Modifier.weight(1.5f),
                color = AetherColors.Success.copy(0.3f),
                onPress = { pressKey("ENTER") },
            )
        }

        Spacer(Modifier.height(12.dp))

        // Common combos
        Text(
            "Quick Combos",
            color = AetherColors.TextSecondary,
            fontSize = 11.sp,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(6.dp))
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            for ((label, keys) in listOf(
                "Ctrl+C" to listOf("LCTRL", "c"),
                "Ctrl+V" to listOf("LCTRL", "v"),
                "Ctrl+X" to listOf("LCTRL", "x"),
                "Ctrl+Z" to listOf("LCTRL", "z"),
                "Alt+F4" to listOf("LALT", "F4"),
                "Alt+Tab" to listOf("LALT", "TAB"),
            )) {
                ComboButton(
                    label = label,
                    modifier = Modifier.weight(1f),
                    onClick = {
                        keys.dropLast(1).forEach { networkManager.sendKeyDown(it) }
                        networkManager.sendKeyDown(keys.last())
                        networkManager.sendKeyUp(keys.last())
                        keys.dropLast(1).reversed().forEach { networkManager.sendKeyUp(it) }
                    }
                )
            }
        }
    }
}

@Composable
fun KeyRow(
    keys: List<String>,
    onPress: (String) -> Unit,
    specialColor: Color? = null,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 3.dp),
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        keys.forEach { key ->
            KeyButton(
                label = key.uppercase(),
                modifier = Modifier.weight(1f),
                color = specialColor ?: AetherColors.SurfaceVariant,
                onPress = { onPress(key) },
            )
        }
    }
}

@Composable
fun KeyButton(label: String, modifier: Modifier = Modifier, color: Color, onPress: () -> Unit) {
    var pressed by remember { mutableStateOf(false) }
    Box(
        modifier = modifier
            .height(40.dp)
            .background(
                if (pressed) color.copy(alpha = 0.8f) else color,
                RoundedCornerShape(6.dp)
            )
            .border(1.dp, AetherColors.Border, RoundedCornerShape(6.dp))
            .pointerInput(Unit) {
                detectTapGestures(
                    onPress = {
                        pressed = true
                        tryAwaitRelease()
                        pressed = false
                        onPress()
                    }
                )
            },
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = AetherColors.TextPrimary,
            fontSize = 10.sp,
            fontWeight = FontWeight.Medium,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
fun RowScope.ModKey(label: String, active: Boolean, onClick: () -> Unit) {
    Box(
        Modifier
            .weight(1f)
            .height(36.dp)
            .background(
                if (active) AetherColors.Primary.copy(0.4f) else AetherColors.SurfaceVariant,
                RoundedCornerShape(8.dp),
            )
            .border(
                1.dp,
                if (active) AetherColors.Primary else AetherColors.Border,
                RoundedCornerShape(8.dp),
            )
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            color = if (active) AetherColors.PrimaryLight else AetherColors.TextSecondary,
            fontSize = 11.sp,
            fontWeight = if (active) FontWeight.Bold else FontWeight.Normal,
        )
    }
}

@Composable
fun ComboButton(label: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier = modifier
            .height(34.dp)
            .background(AetherColors.Surface, RoundedCornerShape(8.dp))
            .border(1.dp, AetherColors.Border, RoundedCornerShape(8.dp))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(label, color = AetherColors.TextSecondary, fontSize = 10.sp)
    }
}
