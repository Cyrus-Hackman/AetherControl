package com.aethercontrol.ui.screens

import androidx.compose.foundation.*
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aethercontrol.network.NetworkManager
import com.aethercontrol.ui.theme.AetherColors

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

@Composable
fun RemoteDesktopScreen(networkManager: NetworkManager, onBack: () -> Unit) {
    LaunchedEffect(Unit) {
        networkManager.requestScreenStream()
    }
    DisposableEffect(Unit) {
        onDispose { networkManager.stopScreenStream() }
    }

    Box(
        Modifier
            .fillMaxSize()
            .background(AetherColors.Background),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                "Remote Desktop",
                color = AetherColors.TextPrimary,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(16.dp))
            CircularProgressIndicator(color = AetherColors.Primary)
            Spacer(Modifier.height(16.dp))
            Text(
                "Connecting to stream...\n\nStage 4 feature — video decoding\nwill be implemented using MediaCodec.",
                color = AetherColors.TextSecondary,
                fontSize = 13.sp,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
            Spacer(Modifier.height(24.dp))
            Button(onClick = onBack, colors = ButtonDefaults.buttonColors(containerColor = AetherColors.Surface)) {
                Text("← Back", color = AetherColors.TextSecondary)
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
