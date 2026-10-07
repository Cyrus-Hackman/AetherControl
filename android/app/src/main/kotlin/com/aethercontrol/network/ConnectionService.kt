package com.aethercontrol.network

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.aethercontrol.R

class ConnectionService : Service() {

    private var wifiLock: WifiManager.WifiLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val pcName = intent?.getStringExtra("PC_NAME") ?: "PC"

        createNotificationChannel()

        val notification = NotificationCompat.Builder(this, "AETHER_CONNECTION")
            .setContentTitle("Connected to $pcName")
            .setContentText("AetherControl is running in the background")
            .setSmallIcon(android.R.drawable.ic_menu_preferences) // fallback icon
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(1, notification)
        }

        acquireWifiLock()

        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        releaseWifiLock()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                "AETHER_CONNECTION",
                "Active Connection",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun acquireWifiLock() {
        val wifiManager = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
        wifiLock = wifiManager?.createWifiLock(
            WifiManager.WIFI_MODE_FULL_HIGH_PERF,
            "AetherControl::WifiLock"
        )
        wifiLock?.acquire()
    }

    private fun releaseWifiLock() {
        wifiLock?.takeIf { it.isHeld }?.release()
        wifiLock = null
    }
}
