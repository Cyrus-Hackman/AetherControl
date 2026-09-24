package com.aethercontrol.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// ── Color palette ─────────────────────────────────────────────────────────────
object AetherColors {
    val Background     = Color(0xFF0D1117)
    val Surface        = Color(0xFF161B22)
    val SurfaceVariant = Color(0xFF21262D)
    val Border         = Color(0xFF30363D)

    val Primary        = Color(0xFF1F6FEB)
    val PrimaryLight   = Color(0xFF58A6FF)
    val PrimaryDark    = Color(0xFF1158C7)

    val Success        = Color(0xFF3FB950)
    val Warning        = Color(0xFFD29922)
    val Error          = Color(0xFFF85149)

    val TextPrimary    = Color(0xFFE6EDF3)
    val TextSecondary  = Color(0xFF8B949E)
    val TextMuted      = Color(0xFF484F58)

    val Gamepad        = Color(0xFF8957E5)
    val Media          = Color(0xFFE3B341)
    val System         = Color(0xFFDA3633)
    val Keyboard       = Color(0xFF3FB950)
    val Touchpad       = Color(0xFF1F6FEB)
}

// ── Dark color scheme ──────────────────────────────────────────────────────────
private val AetherDarkColors = darkColorScheme(
    primary            = AetherColors.Primary,
    onPrimary          = Color.White,
    primaryContainer   = Color(0xFF1F6FEB20),
    onPrimaryContainer = AetherColors.PrimaryLight,
    secondary          = AetherColors.Gamepad,
    tertiary           = AetherColors.Success,
    background         = AetherColors.Background,
    surface            = AetherColors.Surface,
    surfaceVariant     = AetherColors.SurfaceVariant,
    onBackground       = AetherColors.TextPrimary,
    onSurface          = AetherColors.TextPrimary,
    onSurfaceVariant   = AetherColors.TextSecondary,
    outline            = AetherColors.Border,
    error              = AetherColors.Error,
)

// ── Typography ────────────────────────────────────────────────────────────────
val AetherTypography = Typography(
    headlineLarge = TextStyle(
        fontFamily = FontFamily.Default,
        fontWeight = FontWeight.Bold,
        fontSize = 28.sp,
        color = AetherColors.TextPrimary,
    ),
    headlineMedium = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize = 22.sp,
        color = AetherColors.TextPrimary,
    ),
    titleLarge = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 18.sp,
        color = AetherColors.TextPrimary,
    ),
    titleMedium = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 15.sp,
        color = AetherColors.TextPrimary,
    ),
    bodyLarge = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        color = AetherColors.TextPrimary,
    ),
    bodyMedium = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 13.sp,
        color = AetherColors.TextSecondary,
    ),
    labelMedium = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 11.sp,
        color = AetherColors.TextMuted,
        letterSpacing = 0.5.sp,
    ),
)

// ── Theme composable ──────────────────────────────────────────────────────────
@Composable
fun AetherTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = AetherDarkColors,
        typography = AetherTypography,
        content = content,
    )
}
