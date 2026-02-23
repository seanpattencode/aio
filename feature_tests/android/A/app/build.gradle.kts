plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
android {
    namespace = "com.aios.a"
    compileSdk = 34
    defaultConfig { applicationId = "com.aios.a"; minSdk = 24; targetSdk = 34; versionCode = 200 }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_11; targetCompatibility = JavaVersion.VERSION_11 }
    kotlinOptions { jvmTarget = "11" }
}
