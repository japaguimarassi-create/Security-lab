from __future__ import annotations

from typing import Any

PROVIDER_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "volunteer-worker",
        "name": "GPU Mesh Volunteer Worker",
        "mode": "self-hosted-agent",
        "resource_types": ["gpu", "vram", "cpu", "ram", "storage"],
        "status": "supported",
        "free_capacity_guaranteed": False,
        "notes": "A participant runs the signed worker agent on hardware they control.",
    },
    {
        "id": "huggingface-zerogpu",
        "name": "Hugging Face ZeroGPU",
        "mode": "hosted-space-endpoint",
        "resource_types": ["gpu-inference"],
        "status": "supported",
        "free_capacity_guaranteed": False,
        "notes": "Requires a user-deployed Gradio ZeroGPU Space, HF token and provider quota; GPU time is allocated on demand.",
    },
    {
        "id": "kaggle-notebooks",
        "name": "Kaggle Notebooks",
        "mode": "notebook-job",
        "resource_types": ["gpu-notebook", "cpu-notebook"],
        "status": "supported",
        "free_capacity_guaranteed": False,
        "notes": "Private Kaggle kernel jobs are submitted and polled by the optional CLI adapter; the account owner configures accelerator and quotas.",
    },
    {
        "id": "google-colab",
        "name": "Google Colab",
        "mode": "interactive-notebook",
        "resource_types": ["gpu-notebook", "tpu-notebook"],
        "status": "interactive-only",
        "free_capacity_guaranteed": False,
        "notes": "Interactive sessions are not registered as unattended mesh workers.",
    },
    {
        "id": "custom-provider",
        "name": "Authorized Custom Provider",
        "mode": "provider-adapter",
        "resource_types": ["gpu", "vram", "cpu", "ram", "storage"],
        "status": "adapter-required",
        "free_capacity_guaranteed": False,
        "notes": "Requires an explicit contract-compliant adapter and provider credentials.",
    },
)


def list_providers() -> list[dict[str, Any]]:
    return [dict(item) for item in PROVIDER_CATALOG]


def get_provider(provider_id: str) -> dict[str, Any]:
    for item in PROVIDER_CATALOG:
        if item["id"] == provider_id:
            return dict(item)
    raise ValueError("Unknown provider")
