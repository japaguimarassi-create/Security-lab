# KLOD training stage 20%

- Branch: training/20-percent
- Stage: 1 of 5
- Work: one additional SFT epoch
- Cumulative target: 20% of the original five-epoch plan
- Predecessor: Qwen3-1.7B-Base
- Adapter artifact: klod-stage-20-adapter

This branch is configured in setup mode. Edit `data/github/run-request.json` and commit the request on this branch to start the stage.

The request must use `phase: train_stage`, `stage_percent: 20`, the successful teacher-generation run ID, and at least 20 distinct candidate IDs that were manually checked and passed the quality screen. Set previous_stage_run_id to null.

The workflow uses GitHub Actions artifacts to carry forward the LoRA adapter. It requires an NVIDIA CUDA GPU runner. The default CPU runner only validates setup and fails before training; it does not switch models or claim that training occurred. See `docs/GITHUB_TRAINING.md`.
