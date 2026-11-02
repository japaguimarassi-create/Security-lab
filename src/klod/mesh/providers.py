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
        "status": "adapter-required",
        "free_capacity_guaranteed": False,
        "notes": "User-authorized Spaces endpoints only; public quota and availability remain provider-controlled.",
    },
    {
        "id": "kaggle-notebooks",
        "name": "Kaggle Notebooks",
        "mode": "notebook-job",
        "resource_types": ["gpu-notebook", "cpu-notebook"],
        "status": "adapter-required",
        "free_capacity_guaranteed": False,
        "notes": "Notebook sessions are not a persistent general-purpose worker API; use only permitted notebook execution.",
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
