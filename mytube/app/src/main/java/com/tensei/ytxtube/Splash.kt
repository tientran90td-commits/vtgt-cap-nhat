package com.tensei.ytxtube

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Name shown on the opening screen. */
private const val OWNER_NAME = "Tiền"

/** Total time the opening screen stays up before fading away. */
private const val SPLASH_MS = 2_000

private val Red = Color(0xFFE0242F)
private val RedBright = Color(0xFFFF3B3B)
private val RedDeep = Color(0xFFB0102B)

/**
 * TTube opening screen: logo pops in, then the app name, the owner's name and a
 * YouTube-style red loading bar with a moving shine. The real app composes
 * underneath the whole time, so this adds no extra loading.
 * Shown once per cold start (not again on rotation).
 */
@Composable
fun LaunchSplash() {
    var visible by rememberSaveable { mutableStateOf(true) }
    val logoScale = remember { Animatable(0.55f) }
    val logoAlpha = remember { Animatable(0f) }
    val textAlpha = remember { Animatable(0f) }
    val textShift = remember { Animatable(14f) }
    val progress = remember { Animatable(0f) }

    LaunchedEffect(Unit) {
        if (!visible) return@LaunchedEffect
        launch { logoAlpha.animateTo(1f, tween(220)) }
        launch {
            logoScale.animateTo(
                1f,
                spring(dampingRatio = 0.55f, stiffness = Spring.StiffnessMediumLow),
            )
        }
        launch {
            delay(160)
            launch { textAlpha.animateTo(1f, tween(320)) }
            textShift.animateTo(0f, tween(380, easing = FastOutSlowInEasing))
        }
        launch {
            delay(120)
            progress.animateTo(1f, tween(SPLASH_MS - 320, easing = FastOutSlowInEasing))
        }
        delay(SPLASH_MS.toLong())
        visible = false
    }

    val c = MaterialTheme.colorScheme
    AnimatedVisibility(
        visible = visible,
        exit = fadeOut(tween(260)) + scaleOut(tween(260), targetScale = 1.06f),
    ) {
        Box(
            Modifier
                .fillMaxSize()
                .background(c.background)
                .clickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                ) { },
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Image(
                    painter = painterResource(R.drawable.ic_brand),
                    contentDescription = null,
                    modifier = Modifier
                        .size(104.dp)
                        .graphicsLayer {
                            scaleX = logoScale.value
                            scaleY = logoScale.value
                            alpha = logoAlpha.value
                        },
                )
                Spacer(Modifier.height(20.dp))
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier.graphicsLayer {
                        alpha = textAlpha.value
                        translationY = textShift.value * density
                    },
                ) {
                    Text(
                        "TTube",
                        color = c.onBackground,
                        fontSize = 32.sp,
                        fontWeight = FontWeight.ExtraBold,
                        letterSpacing = (-0.5).sp,
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        OWNER_NAME,
                        color = Red,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.SemiBold,
                        letterSpacing = 2.sp,
                    )
                }
                Spacer(Modifier.height(40.dp))
                LoadingBar(
                    progress = progress.value,
                    track = c.onBackground.copy(alpha = 0.10f),
                    modifier = Modifier.graphicsLayer { alpha = textAlpha.value },
                )
            }
        }
    }
}

/** Thin red bar that fills up, with a soft white shine sweeping across it. */
@Composable
private fun LoadingBar(progress: Float, track: Color, modifier: Modifier = Modifier) {
    val shine by rememberInfiniteTransition(label = "splashShine").animateFloat(
        initialValue = -0.4f,
        targetValue = 1.4f,
        animationSpec = infiniteRepeatable(tween(900, easing = LinearEasing), RepeatMode.Restart),
        label = "splashShineOffset",
    )
    Box(
        modifier
            .width(190.dp)
            .height(4.dp)
            .clip(RoundedCornerShape(50))
            .background(track),
    ) {
        Box(
            Modifier
                .fillMaxHeight()
                .fillMaxWidth(progress.coerceIn(0.02f, 1f))
                .clip(RoundedCornerShape(50))
                .background(Brush.horizontalGradient(listOf(RedDeep, Red, RedBright)))
                .drawWithContent {
                    drawContent()
                    val band = size.width * 0.35f
                    val x = size.width * shine
                    drawRect(
                        Brush.horizontalGradient(
                            colors = listOf(Color.Transparent, Color.White.copy(alpha = 0.55f), Color.Transparent),
                            startX = x - band,
                            endX = x + band,
                        ),
                    )
                },
        )
    }
}
