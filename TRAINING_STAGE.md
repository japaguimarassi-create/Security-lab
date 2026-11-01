# KLOD training stage 100%

- Branch: training/100-percent
- Stage: 5 of 5
- Work: one additional SFT epoch
- Cumulative target: 100% of the original five-epoch plan
- Predecessor: training/80-percent
- Adapter artifact: klod-stage-100-adapter

This branch is configured in setup mode. Edit `data/github/run-request.json` and commit the request on this branch to start the stage.

The request must use `phase: train_stage`, `stage_percent: 100`, the successful teacher-generation run ID, and at least 20 distinct candidate IDs that were manually checked and passed the quality screen. Set `previous_stage_run_id` to the successful GitHub Actions run ID for the 80% stage.

The workflow uses GitHub Actions artifacts to carry forward the LoRA adapter. It requires an NVIDIA CUDA GPU runner. The default CPU runner only validates setup and fails before training; it does not switch models or claim that training occurred. See `docs/GITHUB_TRAINING.md`.
