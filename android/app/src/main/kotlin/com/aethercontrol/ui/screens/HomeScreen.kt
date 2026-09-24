package com.aethercontrol.ui.screens

import androidx.compose.animation.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.aethercontrol.network.ComputerInfo
import com.aethercontrol.network.ConnectionState
import com.aethercontrol.network.NetworkManager
import com.aethercontrol.ui.theme.AetherColors

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    networkManager: NetworkManager,
    onNavigate: (String) -> Unit,
) {
    val discovered by networkManager.discoveredComputers.collectAsState()
    val connectionState by networkManager.connectionState.collectAsState()
    val connectedComputer by networkManager.connectedComputer.collectAsState()
    var showManualDialog by remember { mutableStateOf(false) }

    Box(
        Modifier
            .fillMaxSize()
            .background(AetherColors.Background)
    ) {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // ── Header ──────────────────────────────────────────────────────
            item {
                Row(
                    Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            "⚡ AetherControl",
                            color = AetherColors.PrimaryLight,
                            fontSize = 22.sp,
                            fontWeight = FontWeight.ExtraBold,
                        )
                        Text(
                            "Remote control suite",
                            color = AetherColors.TextSecondary,
                            fontSize = 13.sp,
                        )
                    }
                    IconButton(onClick = { networkManager.startDiscovery() }) {
                        Icon(
                            Icons.Filled.Refresh,
                            contentDescription = "Scan",
                            tint = AetherColors.TextSecondary,
                        )
                    }
                }
            }

            // ── Current connection banner ────────────────────────────────────
            if (connectionState == ConnectionState.CONNECTED && connectedComputer != null) {
                item {
                    ConnectedBanner(
                        computer = connectedComputer!!,
                        onDisconnect = { networkManager.disconnect() },
                    )
                }
            }

            // ── Computers ────────────────────────────────────────────────────
            item {
                SectionHeader(text = "My Computers")
            }

            if (discovered.isEmpty()) {
                item {
                    ScanningCard(onManual = { showManualDialog = true })
                }
            } else {
                items(discovered, key = { it.id }) { computer ->
                    ComputerCard(
                        computer = computer,
                        isConnected = connectedComputer?.id == computer.id &&
                                connectionState == ConnectionState.CONNECTED,
                        onConnect = { networkManager.connectTo(computer) },
                        onDisconnect = { networkManager.disconnect() },
                    )
                }
                item {
                    TextButton(
                        onClick = { showManualDialog = true },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(
                            "+ Connect manually",
                            color = AetherColors.TextSecondary,
                            fontSize = 13.sp,
                        )
                    }
                }
            }

            // ── Remote modes ─────────────────────────────────────────────────
            if (connectionState == ConnectionState.CONNECTED) {
                item { SectionHeader(text = "Remote Modes") }
                item {
                    RemoteModesGrid(onNavigate = onNavigate)
                }
            }
        }
    }

    // Manual connect dialog
    if (showManualDialog) {
        ManualConnectDialog(
            onConnect = { host, port ->
                showManualDialog = false
                networkManager.connectTo(
                    ComputerInfo(
                        id = host,
                        name = host,
                        host = host,
                        controlPort = port,
                        fastPort = 7702,
                        streamPort = 7701,
                    )
                )
            },
            onDismiss = { showManualDialog = false },
        )
    }
}

@Composable
fun ConnectedBanner(computer: ComputerInfo, onDisconnect: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(
                Brush.horizontalGradient(
                    listOf(Color(0xFF1F6FEB20), Color(0xFF3FB95020))
                )
            )
            .border(1.dp, AetherColors.Success.copy(alpha = 0.3f), RoundedCornerShape(12.dp))
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(AetherColors.Success)
        )
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                "Connected",
                color = AetherColors.Success,
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
            )
            Text(
                computer.name,
                color = AetherColors.TextPrimary,
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
        TextButton(onClick = onDisconnect) {
            Text("Disconnect", color = AetherColors.Error, fontSize = 12.sp)
        }
    }
}

@Composable
fun ComputerCard(
    computer: ComputerInfo,
    isConnected: Boolean,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = AetherColors.Surface),
        border = BorderStroke(
            width = 1.dp,
            color = if (isConnected) AetherColors.Success.copy(0.4f) else AetherColors.Border,
        ),
    ) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Monitor icon
            Box(
                Modifier
                    .size(48.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(AetherColors.Primary.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Filled.Computer,
                    contentDescription = null,
                    tint = AetherColors.PrimaryLight,
                    modifier = Modifier.size(28.dp),
                )
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    computer.name,
                    color = AetherColors.TextPrimary,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.SemiBold,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        Modifier
                            .size(6.dp)
                            .clip(CircleShape)
                            .background(if (isConnected) AetherColors.Success else AetherColors.TextMuted)
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        if (isConnected) "Connected" else "${computer.host}:${computer.controlPort}",
                        color = AetherColors.TextSecondary,
                        fontSize = 12.sp,
                    )
                }
            }
            if (isConnected) {
                TextButton(onClick = onDisconnect) {
                    Text("Disconnect", color = AetherColors.TextSecondary, fontSize = 12.sp)
                }
            } else {
                Button(
                    onClick = onConnect,
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = AetherColors.Primary),
                ) {
                    Text("Connect", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
fun ScanningCard(onManual: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = AetherColors.Surface),
        border = BorderStroke(1.dp, AetherColors.Border),
    ) {
        Column(
            Modifier.padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            CircularProgressIndicator(
                color = AetherColors.Primary,
                modifier = Modifier.size(32.dp),
                strokeWidth = 2.dp,
            )
            Spacer(Modifier.height(12.dp))
            Text("Scanning for computers...", color = AetherColors.TextSecondary, fontSize = 13.sp)
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = onManual) {
                Text("Enter IP manually", color = AetherColors.PrimaryLight, fontSize = 13.sp)
            }
        }
    }
}

data class RemoteMode(
    val label: String,
    val icon: ImageVector,
    val color: Color,
    val route: String,
)

@Composable
fun RemoteModesGrid(onNavigate: (String) -> Unit) {
    val modes = listOf(
        RemoteMode("Touchpad",   Icons.Filled.TouchApp,   AetherColors.Touchpad, "touchpad"),
        RemoteMode("Keyboard",   Icons.Filled.Keyboard,   AetherColors.Keyboard, "keyboard"),
        RemoteMode("Numpad",     Icons.Filled.Tag,         AetherColors.Success,  "numpad"),
        RemoteMode("Gamepad",    Icons.Filled.SportsEsports, AetherColors.Gamepad, "gamepad"),
        RemoteMode("Desktop",    Icons.Filled.DesktopWindows, AetherColors.PrimaryLight, "remote_desktop"),
        RemoteMode("Media",      Icons.Filled.PlayCircle, AetherColors.Media,    "media"),
        RemoteMode("System",     Icons.Filled.Settings,   AetherColors.System,   "system"),
        RemoteMode("Files",      Icons.Filled.Folder,     AetherColors.Warning,  "file_transfer"),
    )

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        modes.chunked(4).forEach { row ->
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                row.forEach { mode ->
                    RemoteModeButton(
                        mode = mode,
                        modifier = Modifier.weight(1f),
                        onClick = { onNavigate(mode.route) },
                    )
                }
                // Fill remaining slots if row is not full
                repeat(4 - row.size) {
                    Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
fun RemoteModeButton(mode: RemoteMode, modifier: Modifier, onClick: () -> Unit) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(12.dp))
            .background(AetherColors.Surface)
            .border(1.dp, AetherColors.Border, RoundedCornerShape(12.dp))
            .clickable(onClick = onClick)
            .padding(vertical = 14.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Box(
            Modifier
                .size(40.dp)
                .clip(RoundedCornerShape(10.dp))
                .background(mode.color.copy(alpha = 0.15f)),
            contentAlignment = Alignment.Center,
        ) {
            Icon(mode.icon, contentDescription = null, tint = mode.color, modifier = Modifier.size(22.dp))
        }
        Spacer(Modifier.height(6.dp))
        Text(
            mode.label,
            color = AetherColors.TextPrimary,
            fontSize = 11.sp,
            fontWeight = FontWeight.Medium,
        )
    }
}

@Composable
fun SectionHeader(text: String) {
    Text(
        text,
        color = AetherColors.TextSecondary,
        fontSize = 12.sp,
        fontWeight = FontWeight.SemiBold,
        letterSpacing = 1.sp,
        modifier = Modifier.padding(vertical = 4.dp),
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ManualConnectDialog(onConnect: (String, Int) -> Unit, onDismiss: () -> Unit) {
    var host by remember { mutableStateOf("192.168.1.") }
    var port by remember { mutableStateOf("7700") }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = AetherColors.Surface,
        title = {
            Text("Manual Connection", color = AetherColors.TextPrimary, fontWeight = FontWeight.Bold)
        },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it },
                    label = { Text("IP Address") },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = AetherColors.Primary,
                        unfocusedBorderColor = AetherColors.Border,
                        focusedTextColor = AetherColors.TextPrimary,
                        unfocusedTextColor = AetherColors.TextPrimary,
                        focusedLabelColor = AetherColors.PrimaryLight,
                        unfocusedLabelColor = AetherColors.TextSecondary,
                        cursorColor = AetherColors.Primary,
                    ),
                )
                OutlinedTextField(
                    value = port,
                    onValueChange = { port = it },
                    label = { Text("Port") },
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = AetherColors.Primary,
                        unfocusedBorderColor = AetherColors.Border,
                        focusedTextColor = AetherColors.TextPrimary,
                        unfocusedTextColor = AetherColors.TextPrimary,
                        focusedLabelColor = AetherColors.PrimaryLight,
                        unfocusedLabelColor = AetherColors.TextSecondary,
                        cursorColor = AetherColors.Primary,
                    ),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { onConnect(host, port.toIntOrNull() ?: 7700) },
                colors = ButtonDefaults.buttonColors(containerColor = AetherColors.Primary),
            ) { Text("Connect") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = AetherColors.TextSecondary)
            }
        },
    )
}
