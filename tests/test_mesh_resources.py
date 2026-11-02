import pytest

from klod.mesh.registry import ResourceRegistry
from klod.mesh.scheduler import SchedulingError, TaskScheduler


def register(registry, owner="user-1", gpus=None, shared=True):
    return registry.register(
        owner_id=owner,
        provider_id="volunteer-worker",
        cpu_cores=8,
        ram_gib=32,
        storage_gib=100,
        gpus=gpus or [{"name": "GPU", "total_vram_gib": 8, "available_vram_gib": 8}],
        shared=shared,
    )


def test_worker_token_is_returned_once_and_heartbeat_is_authenticated(tmp_path):
    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    registered = register(registry)
    node_id = registered["node_id"]
    assert registry.heartbeat(node_id, "wrong-token", "user-1") is False
    assert registry.heartbeat(node_id, registered["worker_token"], "user-1") is True
    assert registry.list_schedulable("other-user")


def test_owner_private_nodes_are_visible_but_not_shared_to_others(tmp_path):
    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    register(registry, owner="private-owner", shared=False)
    assert len(registry.list_schedulable("private-owner")) == 1
    assert registry.list_schedulable("other-owner") == []


def test_invalid_capacity_is_rejected(tmp_path):
    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    with pytest.raises(ValueError):
        registry.register("u", "provider", 0, 8, 1, [])
    with pytest.raises(ValueError):
        registry.register("u", "provider", 2, 8, 1, [
            {"total_vram_gib": 4, "available_vram_gib": 5}
        ])


def test_scheduler_never_adds_vram_from_separate_devices(tmp_path):
    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    node = register(registry, gpus=[
        {"name": "GPU A", "total_vram_gib": 8, "available_vram_gib": 8},
        {"name": "GPU B", "total_vram_gib": 8, "available_vram_gib": 8},
    ])
    registry.heartbeat(node["node_id"], node["worker_token"], "user-1")
    scheduler = TaskScheduler()
    result = scheduler.plan(
        owner_id="user-1", workload="independent-render-frames", task_count=1,
        nodes=registry.list_schedulable("user-1"), requires_gpu=True,
        min_vram_gib_per_task=12, cpu_cores_per_task=1, ram_gib_per_task=1,
    )
    assert result["status"] == "queued"
    assert result["scheduled_tasks"] == 0


def test_scheduler_splits_independent_jobs_across_real_devices(tmp_path):
    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    first = register(registry, owner="user-1", gpus=[
        {"name": "GPU A", "total_vram_gib": 8, "available_vram_gib": 8},
    ])
    second = register(registry, owner="user-2", gpus=[
        {"name": "GPU B", "total_vram_gib": 12, "available_vram_gib": 12},
    ])
    registry.heartbeat(first["node_id"], first["worker_token"], "user-1")
    registry.heartbeat(second["node_id"], second["worker_token"], "user-2")
    result = TaskScheduler().plan(
        owner_id="user-1", workload="independent-render-frames", task_count=2,
        nodes=registry.list_schedulable("user-1"), requires_gpu=True,
        min_vram_gib_per_task=8, cpu_cores_per_task=1, ram_gib_per_task=2,
    )
    assert result["status"] == "planned"
    assert result["scheduled_tasks"] == 2
    assert len(result["assignments"]) == 2


def test_gpu_workload_requires_per_device_vram_threshold():
    with pytest.raises(SchedulingError):
        TaskScheduler().plan(
            owner_id="u", workload="render", task_count=1, nodes=[],
            requires_gpu=True, min_vram_gib_per_task=0,
        )
