package com.aios.termuxbridge

import android.app.Service
import android.content.Intent
import android.os.Bundle
import android.os.IBinder

class MyResultService : Service() {
    companion object {
        var onResult: ((stdout: String, stderr: String, exitCode: Int) -> Unit)? = null
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        intent?.let {
            val bundle = it.getBundleExtra("result") ?: Bundle()
            val stdout = bundle.getString("stdout") ?: ""
            val stderr = bundle.getString("stderr") ?: ""
            val exitCode = bundle.getInt("exitCode", -1)
            onResult?.invoke(stdout, stderr, exitCode)
        }
        stopSelf()
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
