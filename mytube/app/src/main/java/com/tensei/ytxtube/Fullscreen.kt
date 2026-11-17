package com.tensei.ytxtube

import android.app.Activity
import android.app.PendingIntent
import android.app.PictureInPictureParams
import android.app.RemoteAction
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.drawable.Icon
import androidx.core.content.ContextCompat
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.util.Rational
import androidx.activity.ComponentActivity
import androidx.activity.enableEdgeToEdge
import androidx.core.app.PictureInPictureModeChangedInfo
import androidx.core.util.Consumer
import androidx.lifecycle.Lifecycle
import android.provider.Settings
import android.view.OrientationEventListener
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat










@Stable
class OrientationController(private val activity: Activity) {
    private enum class Forced { Landscape, Portrait }

    private var forced by mutableStateOf<Forced?>(null)
    private var playerOpen = false

    private val listener = object : OrientationEventListener(activity) {
        override fun onOrientationChanged(degrees: Int) {
            if (degrees == ORIENTATION_UNKNOWN) return
            val physicallyLandscape = degrees in 60..120 || degrees in 240..300
            val physicallyPortrait = degrees <= 30 || degrees >= 330
            when {


                forced == Forced.Landscape && physicallyLandscape && autoRotateOn() -> forced = null
                forced == Forced.Portrait && physicallyPortrait -> forced = null
            }
        }
    }

    private fun autoRotateOn() =
        Settings.System.getInt(activity.contentResolver, Settings.System.ACCELEROMETER_ROTATION, 0) == 1

    fun enterFullscreen() { forced = Forced.Landscape }

    /** Leave the player's forced orientation and follow the device again. */
    fun exitFullscreen() {
        forced = null
        apply()
    }

    fun setPlayerOpen(open: Boolean) {
        playerOpen = open
        if (!open) forced = null
        apply()
    }

    fun apply() {
        if (TvMode.isTv) {
            // TVs are physically landscape and must never be rotated into portrait.
            activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
            return
        }
        activity.requestedOrientation = when {
            // Browsing must follow the device: tablets and foldables should be able
            // to stay in landscape instead of being locked to portrait.
            !playerOpen -> ActivityInfo.SCREEN_ORIENTATION_USER
            forced == Forced.Landscape -> ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
            forced == Forced.Portrait -> ActivityInfo.SCREEN_ORIENTATION_PORTRAIT
            else -> ActivityInfo.SCREEN_ORIENTATION_USER
        }
    }

    @Composable
    fun Bind(playerOpen: Boolean) {
        DisposableEffect(Unit) {
            if (listener.canDetectOrientation()) listener.enable()
            onDispose { listener.disable() }
        }
        LaunchedEffect(playerOpen, forced) { setPlayerOpen(playerOpen) }
    }
}

@Composable
fun rememberOrientationController(activity: Activity) = remember(activity) { OrientationController(activity) }


@Composable
fun SystemBarsHidden(hidden: Boolean) {
    val view = LocalView.current
    val dark = isDarkTheme()
    DisposableEffect(hidden, dark) {
        val activity = view.context as? ComponentActivity ?: (view.context as? Activity)
        val window = activity?.window
        val controller = window?.let { WindowCompat.getInsetsController(it, view) }
        fun restoreBars() {
            controller?.show(WindowInsetsCompat.Type.systemBars())
            controller?.isAppearanceLightStatusBars = !dark
            controller?.isAppearanceLightNavigationBars = !dark
            if (activity is ComponentActivity) {
                val barStyle = if (dark) {
                    androidx.activity.SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
                } else {
                    androidx.activity.SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT)
                }
                runCatching {
                    activity.enableEdgeToEdge(statusBarStyle = barStyle, navigationBarStyle = barStyle)
                    controller?.isAppearanceLightStatusBars = !dark
                    controller?.isAppearanceLightNavigationBars = !dark
                }
            }
        }

        if (hidden) {
            controller?.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            controller?.hide(WindowInsetsCompat.Type.systemBars())
        } else {
            restoreBars()
        }
        onDispose { restoreBars() }
    }
}






@Stable
class PipController(private val activity: ComponentActivity) {
    var active by mutableStateOf(activity.isInPictureInPictureMode)
        private set
    val supported = activity.packageManager.hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)

    var videoBounds: Rect? = null

    /** Set by the headphones button: closing PiP should keep the audio going. */
    private var keepPlayingOnClose = false
    private var playing = true
    private var lastAspect = 16f / 9f
    private var autoEnter = false

    /** Play/pause + headphones (background audio) buttons shown inside the PiP window. */
    private fun pipActions(): List<RemoteAction> {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.O) return emptyList()
        fun action(id: String, code: Int, icon: Int, title: String): RemoteAction {
            val intent = Intent(id).setPackage(activity.packageName)
            val pending = PendingIntent.getBroadcast(
                activity,
                code,
                intent,
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
            return RemoteAction(Icon.createWithResource(activity, icon), title, title, pending)
        }
        return listOf(
            if (playing) {
                action(ACTION_TOGGLE, 1, R.drawable.ic_pip_pause, I18n.t("p_pause", "Pause"))
            } else {
                action(ACTION_TOGGLE, 1, R.drawable.ic_pip_play, I18n.t("p_play", "Play"))
            },
            action(ACTION_BACKGROUND, 2, R.drawable.ic_pip_headphones, I18n.t("p_background_audio", "Play in background")),
        )
    }

    private fun params(aspect: Float, autoEnterEnabled: Boolean?): PictureInPictureParams {
        val ratio = aspect.coerceIn(0.42f, 2.38f)
        return PictureInPictureParams.Builder()
            .setAspectRatio(Rational((ratio * 1000).toInt(), 1000))
            .setActions(pipActions())
            .apply {
                videoBounds?.let { b -> setSourceRectHint(android.graphics.Rect(b.left.toInt(), b.top.toInt(), b.right.toInt(), b.bottom.toInt())) }
                if (autoEnterEnabled != null && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
                    setAutoEnterEnabled(autoEnterEnabled)
                }
            }
            .build()
    }

    fun enter(videoAspect: Float): Boolean {
        if (!supported) return false
        keepPlayingOnClose = false
        lastAspect = videoAspect
        return runCatching { activity.enterPictureInPictureMode(params(videoAspect, null)) }.getOrDefault(false)
    }

    fun updateAutoPip(enabled: Boolean, videoAspect: Float = 16f / 9f) {
        if (!supported) return
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) {
            autoEnter = enabled
            if (enabled) lastAspect = videoAspect
            runCatching { activity.setPictureInPictureParams(params(lastAspect, enabled)) }
        }
    }

    /** Keeps the play/pause button in the PiP window in sync with the player. */
    fun updatePlaying(isPlaying: Boolean) {
        if (playing == isPlaying) return
        playing = isPlaying
        if (!supported || android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.O) return
        val auto = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) autoEnter else null
        runCatching { activity.setPictureInPictureParams(params(lastAspect, auto)) }
    }

    @Composable
    fun Bind(onClosed: () -> Unit, onTogglePlay: () -> Unit) {
        DisposableEffect(activity) {
            val listener = Consumer<PictureInPictureModeChangedInfo> { info ->
                active = info.isInPictureInPictureMode
                if (info.isInPictureInPictureMode) {
                    keepPlayingOnClose = false
                } else if (!activity.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) {
                    if (keepPlayingOnClose) keepPlayingOnClose = false else onClosed()
                }
            }
            activity.addOnPictureInPictureModeChangedListener(listener)

            val receiver = object : BroadcastReceiver() {
                override fun onReceive(context: Context, intent: Intent) {
                    when (intent.action) {
                        ACTION_TOGGLE -> onTogglePlay()
                        ACTION_BACKGROUND -> {
                            // Close the PiP window but keep the sound playing in the background.
                            keepPlayingOnClose = true
                            activity.moveTaskToBack(true)
                        }
                    }
                }
            }
            val filter = IntentFilter().apply {
                addAction(ACTION_TOGGLE)
                addAction(ACTION_BACKGROUND)
            }
            ContextCompat.registerReceiver(activity, receiver, filter, ContextCompat.RECEIVER_NOT_EXPORTED)

            onDispose {
                activity.removeOnPictureInPictureModeChangedListener(listener)
                runCatching { activity.unregisterReceiver(receiver) }
            }
        }
    }

    private companion object {
        const val ACTION_TOGGLE = "com.tensei.ytxtube.PIP_TOGGLE"
        const val ACTION_BACKGROUND = "com.tensei.ytxtube.PIP_BACKGROUND"
    }
}


val LocalPictureInPicture = staticCompositionLocalOf<PipController?> { null }
