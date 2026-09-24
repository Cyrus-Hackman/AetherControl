package com.aethercontrol.ui.screens

import androidx.compose.runtime.Composable
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.aethercontrol.network.NetworkManager

sealed class Screen(val route: String) {
    object Home        : Screen("home")
    object Touchpad    : Screen("touchpad")
    object Keyboard    : Screen("keyboard")
    object Numpad      : Screen("numpad")
    object Gamepad     : Screen("gamepad")
    object RemoteDesk  : Screen("remote_desktop")
    object Media       : Screen("media")
    object System      : Screen("system")
    object FileTransfer: Screen("file_transfer")
}

@Composable
fun AppNavHost(navController: NavHostController) {
    val networkManager: NetworkManager = viewModel()

    NavHost(navController = navController, startDestination = Screen.Home.route) {
        composable(Screen.Home.route) {
            HomeScreen(
                networkManager = networkManager,
                onNavigate = { route -> navController.navigate(route) }
            )
        }
        composable(Screen.Touchpad.route) {
            TouchpadScreen(
                networkManager = networkManager,
                onBack = { navController.popBackStack() }
            )
        }
        composable(Screen.Keyboard.route) {
            KeyboardScreen(
                networkManager = networkManager,
                onBack = { navController.popBackStack() }
            )
        }
        composable(Screen.Numpad.route) {
            NumpadScreen(
                networkManager = networkManager,
                onBack = { navController.popBackStack() }
            )
        }
        composable(Screen.Gamepad.route) {
            GamepadScreen(
                networkManager = networkManager,
                onBack = { navController.popBackStack() }
            )
        }
        composable(Screen.RemoteDesk.route) {
            RemoteDesktopScreen(
                networkManager = networkManager,
                onBack = { navController.popBackStack() }
            )
        }
        composable(Screen.Media.route) {
            MediaScreen(
                networkManager = networkManager,
                onBack = { navController.popBackStack() }
            )
        }
        composable(Screen.System.route) {
            SystemScreen(
                networkManager = networkManager,
                onBack = { navController.popBackStack() }
            )
        }
        composable(Screen.FileTransfer.route) {
            FileTransferScreen(
                networkManager = networkManager,
                onBack = { navController.popBackStack() }
            )
        }
    }
}
