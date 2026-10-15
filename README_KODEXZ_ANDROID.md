# Kodexz Android v6 — build workspace

This branch is prepared to build the Kodexz Android source ZIP with GitHub Actions.

## Important status

The complete source archive has **not yet been uploaded to this repository**. Upload `Kodexz_Android_v6_Source.zip` to the root of this branch from the GitHub website. The archive should contain the `Kodexz_Android_v6/` directory at its root.

## Build

After uploading the ZIP, open **Actions → Build Kodexz Android from source ZIP → Run workflow**. The workflow unpacks the archive, installs Java/Android SDK/Gradle, builds the debug APK, and publishes it as an artifact named `Kodexz-Android-debug-APK`.

## Project facts

- Android application ID: `com.kodexz.app`
- Minimum Android: 8.0 (API 26)
- Compile SDK: 35
- Java: 17
- This build is a debug APK, not a Play Store release.
- Do not commit OAuth client secrets or access tokens.
