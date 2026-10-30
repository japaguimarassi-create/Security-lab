# VoxelForge Arena

A mobile-first, offline-capable voxel FPS prototype inspired by the *genre and interaction loop* of LAVOICE, implemented independently.

## What is in this build

- First-person 3D voxel arena with destructible terrain.
- Resource extraction: remove terrain blocks to earn crafting material.
- Deterministic text command parser in Portuguese, with a shared command path for voice transcription.
- Android speech-to-text bridge using the system recognizer, with offline preference where the installed recognition service supports it.
- Preview/confirmation before a blueprint consumes resources.
- Procedural weapon assembly, projectile effects, creatures, turrets, shields, vehicles and abilities.
- Mobile joystick, swipe-look, jump, extract, fire, text and voice controls.
- Local blueprint/history storage; no account or cloud API required.
- GitHub Actions Android debug APK build and validation.

## Build

Push to the `voxelforge-android` branch or run the **Android APK** workflow manually. The workflow installs the pinned Three.js runtime, validates JavaScript, builds the Android app with Gradle, checks the APK package metadata and uploads the APK as an artifact.

The generated APK is a debug-signed development build. It is suitable for installing and testing; a production release needs a private release keystore and separate signing configuration.

## Voice

The Android button invokes Android's installed speech-recognition service and requests offline recognition. Actual offline availability depends on the recognition provider and whether its Portuguese (Brazil) language model is installed. Text entry always remains available and uses the exact same parser.

## Current scope

This is an independent playable foundation, not a port of LAVOICE and not a claim of feature parity with its private implementation. The first build focuses on movement, voxel extraction/destruction, command parsing, crafting, basic combat and local AI. Online multiplayer/cross-play, advanced rigid-body physics, a large content pack and a bundled offline speech model are later milestones.

## Tech

- Android host: Java / Android SDK
- Game runtime: Three.js / WebGL
- Build: Gradle 8.9, Android Gradle Plugin 8.7.3, JDK 17
- Rendering: WebGL, capped pixel ratio and low-overhead geometry
