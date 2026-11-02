from __future__ import annotations

import math
import uuid
from typing import Any


class SchedulingError(ValueError):
    pass


class TaskScheduler:
    def plan(self, owner_id: str, workload: str, task_count: int,
             nodes: list[dict[str, Any]], requires_gpu: bool = True,
             min_vram_gib_per_task: float = 0,
             cpu_cores_per_task: float = 1,
             ram_gib_per_task: float = 1,
             max_runtime_seconds_per_task: int = 300) -> dict[str, Any]:
        if not owner_id or len(owner_id) > 128:
            raise SchedulingError("Invalid owner")
        if not workload or len(workload) > 80:
            raise SchedulingError("Invalid workload")
        if not 1 <= task_count <= 10000:
            raise SchedulingError("task_count must be between 1 and 10000")
        if not 1 <= max_runtime_seconds_per_task <= 86400:
            raise SchedulingError("runtime budget must be between 1 and 86400 seconds")
        if not math.isfinite(min_vram_gib_per_task) or min_vram_gib_per_task < 0:
            raise SchedulingError("min_vram_gib_per_task must be non-negative")
        if not math.isfinite(cpu_cores_per_task) or cpu_cores_per_task <= 0:
            raise SchedulingError("cpu_cores_per_task must be positive")
        if not math.isfinite(ram_gib_per_task) or ram_gib_per_task <= 0:
            raise SchedulingError("ram_gib_per_task must be positive")
        if requires_gpu and min_vram_gib_per_task <= 0:
            raise SchedulingError("GPU workloads require a positive per-device VRAM threshold")

        remaining = task_count
        assignments = []
        ordered_nodes = sorted(nodes, key=lambda node: (
            bool(node.get("shared")), -float(node.get("cpu_available", 0))
        ))
        for node in ordered_nodes:
            if remaining <= 0:
                break
            if not node.get("online", False):
                continue
            cpu_slots = int(float(node.get("cpu_available", 0)) // cpu_cores_per_task)
            ram_slots = int(float(node.get("ram_available_gib", 0)) // ram_gib_per_task)
            slots = min(cpu_slots, ram_slots)
            selected_gpus = []
            if requires_gpu:
                for gpu in node.get("gpus", []):
                    available = float(gpu.get("available_vram_gib", 0))
                    max_task_seconds = int(gpu.get("max_task_seconds", 86400))
                    if available >= min_vram_gib_per_task and max_task_seconds >= max_runtime_seconds_per_task:
                        selected_gpus.append({
                            "index": int(gpu.get("index", 0)),
                            "name": str(gpu.get("name", "GPU"))[:120],
                            "available_vram_gib": available,
                            "required_vram_gib": min_vram_gib_per_task,
                            "max_task_seconds": max_task_seconds,
                        })
                slots = min(slots, len(selected_gpus))
            count = min(remaining, max(0, slots))
            if count:
                assignments.append({
                    "node_id": node["node_id"],
                    "provider_id": node["provider_id"],
                    "task_start": task_count - remaining,
                    "task_count": count,
                    "gpu_devices": selected_gpus[:count],
                    "cpu_cores_per_task": cpu_cores_per_task,
                    "ram_gib_per_task": ram_gib_per_task,
                })
                remaining -= count

        scheduled = task_count - remaining
        if scheduled == 0:
            status = "queued"
        elif remaining:
            status = "partially_scheduled"
        else:
            status = "planned"
        return {
            "job_id": str(uuid.uuid4()),
            "owner_id": owner_id,
            "workload": workload,
            "status": status,
            "requested_tasks": task_count,
            "scheduled_tasks": scheduled,
            "queued_tasks": remaining,
            "requires_gpu": requires_gpu,
            "min_vram_gib_per_task": min_vram_gib_per_task,
            "max_runtime_seconds_per_task": max_runtime_seconds_per_task,
            "assignments": assignments,
            "execution_started": False,
            "created_at": __import__("time").time(),
        }
