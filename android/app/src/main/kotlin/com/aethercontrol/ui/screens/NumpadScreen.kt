package com.aethercontrol.ui.screens

import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aethercontrol.network.NetworkManager
import com.aethercontrol.ui.theme.AetherColors

/**
 * Numeric keypad screen
 * 7 8 9
 * 4 5 6
 * 1 2 3
 * 0 . ENTER
 * + - * /
 */
@Composable
fun NumpadScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    fun press(key: String) {
        networkManager.sendKeyDown(key)
        networkManager.sendKeyUp(key)
    }

    val numpadMap = mapOf(
        "0" to "KP0", "1" to "KP1", "2" to "KP2", "3" to "KP3",
        "4" to "KP4", "5" to "KP5", "6" to "KP6", "7" to "KP7",
        "8" to "KP8", "9" to "KP9", "." to "KPDOT",
        "↵" to "KPENTER", "+" to "KPPLUS", "−" to "KPMINUS",
        "×" to "KPASTERISK", "÷" to "KPSLASH", "⌫" to "BACKSPACE",
    )

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
            Text("Numeric Keypad", color = AetherColors.TextPrimary, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        }

        Spacer(Modifier.weight(1f))

        Column(
            Modifier.padding(horizontal = 32.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            NumpadRow(listOf("7", "8", "9"), numpadMap, ::press)
            NumpadRow(listOf("4", "5", "6"), numpadMap, ::press)
            NumpadRow(listOf("1", "2", "3"), numpadMap, ::press)
            NumpadRow(listOf("0", ".", "⌫"), numpadMap, ::press)
            NumpadRow(listOf("+", "−", "×", "÷"), numpadMap, ::press)
            // Big enter
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(56.dp)
                    .background(AetherColors.Success.copy(0.2f), RoundedCornerShape(12.dp))
                    .border(1.dp, AetherColors.Success.copy(0.4f), RoundedCornerShape(12.dp))
                    .clickable { press("KPENTER") },
                contentAlignment = Alignment.Center,
            ) {
                Text("↵ ENTER", color = AetherColors.Success, fontWeight = FontWeight.Bold, fontSize = 16.sp)
            }
        }

        Spacer(Modifier.weight(1f))
    }
}

@Composable
fun NumpadRow(labels: List<String>, keyMap: Map<String, String>, onPress: (String) -> Unit) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        labels.forEach { label ->
            val bgColor = when (label) {
                "⌫" -> AetherColors.Error.copy(0.2f)
                "+", "−", "×", "÷" -> AetherColors.Gamepad.copy(0.2f)
                else -> AetherColors.Surface
            }
            val borderColor = when (label) {
                "⌫" -> AetherColors.Error.copy(0.4f)
                "+", "−", "×", "÷" -> AetherColors.Gamepad.copy(0.4f)
                else -> AetherColors.Border
            }
            Box(
                Modifier
                    .weight(1f)
                    .height(64.dp)
                    .background(bgColor, RoundedCornerShape(12.dp))
                    .border(1.dp, borderColor, RoundedCornerShape(12.dp))
                    .clickable { keyMap[label]?.let { onPress(it) } ?: onPress(label) },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    label,
                    color = AetherColors.TextPrimary,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}
