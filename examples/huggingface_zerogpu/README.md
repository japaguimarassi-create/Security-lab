---
title: GPU Mesh ZeroGPU Bridge
sdk: gradio
app_file: app.py
pinned: false
---

This Space exposes only GPU Mesh's built-in CUDA workloads and CPU SHA-256 task. GPU functions use `@spaces.GPU` and cap each call at 120 seconds. Deploy it as a private Space when possible, then configure the local Mesh bridge with its Space ID and an HF access token.

Install the project from the repository root in the Space's build environment by using the accompanying `requirements.txt`.
