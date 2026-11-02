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
