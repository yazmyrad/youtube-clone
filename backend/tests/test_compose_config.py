import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
NGINX_CONF = ROOT / "infra" / "nginx" / "default.conf"


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


def test_nginx_resolves_upstreams_per_request() -> None:
    """A literal host is resolved once, so a recreated container would give 502s until reload."""
    conf = NGINX_CONF.read_text()

    assert "resolver 127.0.0.11" in conf
    targets = re.findall(r"^\s*proxy_pass\s+([^;]+);", conf, re.MULTILINE)
    assert targets
    assert all(target.startswith("$") for target in targets)


def test_worker_has_time_to_hand_its_job_back() -> None:
    worker = yaml.safe_load(COMPOSE.read_text())["services"]["worker"]

    assert worker["stop_grace_period"] == "30s"
