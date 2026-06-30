"""Tests for stack status helpers."""
from services.observability.metrics import normalize_path
from services.observability.stack import _derive_status, _index_containers, _merge_service_status


def test_normalize_path_collapses_uuid_segments() -> None:
    topic_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    path = f"/api/research/topics/{topic_id}"
    assert normalize_path(path) == "/api/research/topics/{id}"


def test_index_containers_maps_compose_service_labels() -> None:
    containers = [
        {
            "name": "content-engine-worker-1",
            "compose_service": ["worker"],
            "state": "running",
        }
    ]
    indexed = _index_containers(containers)
    assert indexed["worker"]["name"] == "content-engine-worker-1"


def test_merge_service_status_marks_worker_running_when_celery_pings() -> None:
    services = _merge_service_status(
        containers=[],
        probes={"redis": {"status": "ok"}},
        celery={"workers_online": 1, "worker_names": ["celery@worker"]},
        queues={"beat_lock_present": True},
    )
    worker = next(s for s in services if s["name"] == "worker")
    beat = next(s for s in services if s["name"] == "beat")
    assert worker["status"] == "running"
    assert beat["status"] == "running"


def test_derive_status_marks_down_when_probe_and_container_missing() -> None:
    status = _derive_status(
        "nginx",
        "proxy",
        container=None,
        probe={"status": "down", "detail": "connection_refused"},
        celery={},
        queues={},
    )
    assert status == "down"
