from klod.mesh.registry import ResourceRegistry


def test_resource_reservations_are_atomic_and_per_gpu(tmp_path):
    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    worker = registry.register(
        owner_id="owner",
        provider_id="volunteer-worker",
        cpu_cores=4,
        ram_gib=8,
        storage_gib=0,
        gpus=[
            {"name": "GPU A", "total_vram_gib": 8, "available_vram_gib": 8},
            {"name": "GPU B", "total_vram_gib": 8, "available_vram_gib": 8},
        ],
        shared=True,
    )
    assert registry.heartbeat(
        worker["node_id"], worker["worker_token"], owner_id=None,
        cpu_available=4, ram_available_gib=8, storage_available_gib=0,
        gpus=[
            {"name": "GPU A", "total_vram_gib": 8, "available_vram_gib": 8},
            {"name": "GPU B", "total_vram_gib": 8, "available_vram_gib": 8},
        ],
    )
    assert registry.reserve_capacity("task-a", worker["node_id"], 0, 1, 2, 5, 600)
    nodes = registry.list_schedulable("other-user", include_shared=True)
    assert nodes[0]["cpu_available"] == 3
    assert nodes[0]["ram_available_gib"] == 6
    assert nodes[0]["gpus"][0]["available_vram_gib"] == 3
    assert nodes[0]["gpus"][1]["available_vram_gib"] == 8
    assert not registry.reserve_capacity("task-b", worker["node_id"], 0, 1, 1, 4, 600)
    assert registry.reserve_capacity("task-c", worker["node_id"], 1, 1, 1, 4, 600)
    assert registry.release_capacity("task-a")
    nodes = registry.list_schedulable("other-user", include_shared=True)
    assert nodes[0]["gpus"][0]["available_vram_gib"] == 8


def test_worker_token_authentication_and_revocation(tmp_path):
    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    worker = registry.register("owner", "volunteer-worker", 2, 4, 0, [])
    assert registry.authenticate_worker(worker["node_id"], worker["worker_token"])
    assert not registry.authenticate_worker(worker["node_id"], "wrong")
    assert registry.revoke(worker["node_id"], "owner")
    assert not registry.authenticate_worker(worker["node_id"], worker["worker_token"])


def test_scheduler_respects_provider_gpu_maximum_task_duration(tmp_path):
    from klod.mesh.scheduler import TaskScheduler

    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    worker = registry.register(
        owner_id="owner",
        provider_id="huggingface-zerogpu",
        cpu_cores=2,
        ram_gib=8,
        storage_gib=0,
        gpus=[{
            "name": "ZeroGPU large",
            "total_vram_gib": 48,
            "available_vram_gib": 48,
            "max_task_seconds": 120,
        }],
        shared=True,
    )
    assert registry.heartbeat(
        worker["node_id"], worker["worker_token"], owner_id=None,
        cpu_available=2, ram_available_gib=8, storage_available_gib=0,
        gpus=[{
            "name": "ZeroGPU large",
            "total_vram_gib": 48,
            "available_vram_gib": 48,
            "max_task_seconds": 120,
        }],
    )
    nodes = registry.list_schedulable("other", include_shared=True)
    scheduler = TaskScheduler()
    too_long = scheduler.plan(
        owner_id="other", workload="gpu-matmul", task_count=1,
        nodes=nodes, requires_gpu=True, min_vram_gib_per_task=1,
        max_runtime_seconds_per_task=300,
    )
    fits = scheduler.plan(
        owner_id="other", workload="gpu-matmul", task_count=1,
        nodes=nodes, requires_gpu=True, min_vram_gib_per_task=1,
        max_runtime_seconds_per_task=120,
    )
    assert too_long["scheduled_tasks"] == 0
    assert fits["scheduled_tasks"] == 1


def test_gpu_maximum_runtime_rejects_fractional_and_boolean_values(tmp_path):
    registry = ResourceRegistry(str(tmp_path / "mesh.sqlite"))
    with pytest.raises(ValueError, match="max_task_seconds"):
        registry.register(
            "owner", "provider", 2, 4, 0,
            [{"total_vram_gib": 8, "available_vram_gib": 8, "max_task_seconds": 120.5}],
        )
    with pytest.raises(ValueError, match="max_task_seconds"):
        registry.register(
            "owner", "provider", 2, 4, 0,
            [{"total_vram_gib": 8, "available_vram_gib": 8, "max_task_seconds": True}],
        )
