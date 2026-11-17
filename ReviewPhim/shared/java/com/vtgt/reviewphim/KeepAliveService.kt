package com.vtgt.reviewphim

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder
import android.os.PowerManager

/** Giữ app chạy khi tắt màn hình / chuyển app trong lúc làm video (Android hay tắt app chạy nền). */
class KeepAliveService : Service() {
    private var lock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH, "Đang làm video", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, packageManager.getLaunchIntentForPackage(packageName) ?: Intent(),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = Notification.Builder(this, CH)
            .setContentTitle(getString(R.string.app_name) + " đang làm việc")
            .setContentText(intent?.getStringExtra("text") ?: "Đang làm video...")
            .setSmallIcon(R.drawable.ic_stat)
            .setContentIntent(open)
            .setOngoing(true)
            .build()
        startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        if (lock == null) {
            lock = getSystemService(PowerManager::class.java)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "reviewphim:work").apply { acquire(14 * 60 * 60 * 1000L) }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        lock?.let { if (it.isHeld) it.release() }
        lock = null
        super.onDestroy()
    }

    companion object {
        private const val CH = "work"

        fun start(ctx: Context, text: String) {
            try {
                ctx.startForegroundService(Intent(ctx, KeepAliveService::class.java).putExtra("text", text))
            } catch (e: Exception) {
                // không mở được dịch vụ nền (máy chặn) -> vẫn làm bình thường khi app đang mở
            }
        }

        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, KeepAliveService::class.java))
        }
    }
}
