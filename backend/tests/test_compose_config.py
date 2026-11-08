from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "compose.yaml"


def _is_host_path(volume: str | dict) -> bool:
    if isinstance(volume, dict):
        return volume["type"] == "bind"
    return volume.startswith((".", "/", "~"))


def test_deploy_stack_has_no_host_bind_mounts() -> None:
    """The clean-install test runs compose from inside a container, on the host's Docker daemon.

    Host paths resolve on that daemon, so the files must be built into images instead.
    """
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    binds = [
        f"{name}: {volume}"
        for name, service in services.items()
        for volume in service.get("volumes", [])
        if _is_host_path(volume)
    ]

    assert binds == []


def test_worker_is_not_reachable_and_has_no_egress() -> None:
    config = yaml.safe_load(COMPOSE.read_text())
    worker = config["services"]["worker"]

    assert "ports" not in worker
    assert worker["networks"]
    assert all(config["networks"][name]["internal"] is True for name in worker["networks"])
