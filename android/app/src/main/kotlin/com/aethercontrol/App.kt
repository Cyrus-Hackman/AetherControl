package com.aethercontrol

import android.app.Application
import android.util.Log

class App : Application() {
    companion object {
        private const val TAG = "AetherControl"
        lateinit var instance: App
            private set
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        Log.i(TAG, "AetherControl started")
    }
}
