plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val vCode = (project.findProperty("vCode") as String?)?.toIntOrNull() ?: 1

android {
    namespace = "com.vtgt.reviewphim"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.vtgt.reviewphim"
        minSdk = 29
        targetSdk = 35
        versionCode = vCode
        versionName = "1.0.$vCode"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "UPDATE_REPO", "\"tientran90td-commits/vtgt-cap-nhat\"")
        buildConfigField("String", "UPDATE_TAG", "\"reviewphim\"")
        buildConfigField("String", "UPDATE_ASSET", "\"ReviewPhim.apk\"")
    }

    signingConfigs {
        create("app") {
            // khóa ký cố định để bản mới cài đè được lên bản cũ (app cá nhân, phát hành qua GitHub Releases)
            storeFile = file("../keystore/reviewphim.jks")
            storePassword = "reviewphim"
            keyAlias = "reviewphim"
            keyPassword = "reviewphim"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("app")
        }
        debug {
            signingConfig = signingConfigs.getByName("app")
        }
    }

    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "x86_64")
            isUniversalApk = false
        }
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true   // yt-dlp / ffmpeg chạy dưới dạng file thực thi -> phải giải nén thư viện
        }
        jniLibs {
            pickFirsts += setOf("**/libc++_shared.so")
        }
        resources {
            excludes += setOf("META-INF/DEPENDENCIES", "META-INF/LICENSE*", "META-INF/NOTICE*")
        }
    }

    // code / tài nguyên dùng chung với app MangaRecap (thư mục ../shared)
    sourceSets["main"].apply {
        java.srcDir("../shared/java")
        res.srcDir("../shared/res")
        assets.srcDir("../shared/assets")
        jniLibs.srcDir("../shared/jniLibs")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    val media3 = "1.5.1"
    val ydl = "0.17.4"
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("androidx.media3:media3-transformer:$media3")
    implementation("androidx.media3:media3-effect:$media3")
    implementation("androidx.media3:media3-common:$media3")
    implementation("com.google.mlkit:text-recognition-chinese:16.0.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0")   // VieNeu-TTS chạy trên máy
    implementation("io.github.junkfood02.youtubedl-android:library:$ydl")
    implementation("io.github.junkfood02.youtubedl-android:ffmpeg:$ydl")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
}
