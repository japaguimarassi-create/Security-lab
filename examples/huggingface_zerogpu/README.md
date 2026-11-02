---
title: GPU Mesh ZeroGPU Bridge
sdk: gradio
app_file: app.py
pinned: false
---

This Space exposes only GPU Mesh's built-in CUDA workloads and CPU SHA-256 task. GPU functions use `@spaces.GPU` and cap each call at 120 seconds. Deploy it as a private Space when possible, then configure the local Mesh bridge with its Space ID and an HF access token.

Install the project from the repository root in the Space's build environment by using the accompanying `requirements.txt`.


## Space configuration

In the Space settings, configure these variables:

- `HF_ZEROGPU_SIZE=large` (or `xlarge`)
- `GPU_MESH_HF_MAX_TASK_SECONDS=120`

The GPU function is decorated with the matching `@spaces.GPU(size=...)` setting. The Space exposes `/mesh_profile`; the local worker reads this profile before registering any GPU resources. Its `GPU_MESH_HF_ZEROGPU_SIZE` must match the Space setting. A mismatch aborts enrollment instead of advertising hardware the Space does not provide.

The `large` profile advertises 48 GiB and a 1× quota multiplier. `xlarge` advertises 96 GiB and a 2× quota multiplier. The profile and configured maximum task duration are checked remotely before worker registration.
