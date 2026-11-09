import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"
COMPOSE_DEV = ROOT / "compose.dev.yaml"
MAKEFILE = ROOT / "Makefile"
NGINX_DIR = ROOT / "infra" / "nginx"
NGINX_CONF = NGINX_DIR / "default.conf"


class _ComposeLoader(yaml.SafeLoader):
    """Also reads compose's !override tag, which yaml.safe_load refuses."""


_ComposeLoader.add_constructor(
    "!override", lambda loader, node: loader.construct_sequence(node, deep=True)
)


def _dev_service(name: str) -> dict:
    config = yaml.load(COMPOSE_DEV.read_text(), Loader=_ComposeLoader)  # noqa: S506 - a SafeLoader
    return config["services"][name]


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
    conf += (NGINX_DIR / "spa-dev" / "location.inc").read_text()
    targets = re.findall(r"^\s*proxy_pass\s+([^;]+);", conf, re.MULTILINE)
    assert targets
    assert all(target.startswith("$") for target in targets)


def test_every_nginx_include_is_built_into_the_image() -> None:
    """The dev stack mounts the whole directory, so a missing COPY would only break a deploy."""
    conf = NGINX_CONF.read_text()
    includes = set(re.findall(r"include /etc/nginx/conf\.d/([\w.]+);", conf))
    copy_line = next(
        line for line in (NGINX_CONF.parent / "Dockerfile").read_text().splitlines()
        if line.startswith("COPY default.conf")
    )  # fmt: skip

    assert includes
    assert includes <= set(copy_line.split())


def test_minio_publishes_no_ports() -> None:
    services = yaml.safe_load(COMPOSE.read_text())["services"]

    assert "ports" not in services["minio"]


def test_worker_has_time_to_hand_its_job_back() -> None:
    worker = yaml.safe_load(COMPOSE.read_text())["services"]["worker"]

    assert worker["stop_grace_period"] == "30s"


def test_only_the_worker_image_has_ffmpeg() -> None:
    services = yaml.safe_load(COMPOSE.read_text())["services"]

    assert services["worker"]["build"]["target"] == "worker"
    assert services["api"]["build"] == "backend"
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text()
    install = dockerfile.index("--no-install-recommends ffmpeg")
    assert dockerfile.index("AS worker") < install < dockerfile.index("AS api")


def test_worker_files_are_on_a_volume_with_resource_limits() -> None:
    worker = yaml.safe_load(COMPOSE.read_text())["services"]["worker"]
    scratch = worker["environment"]["WORKER_SCRATCH_DIR"]

    assert f"worker-scratch:{scratch}" in worker["volumes"]
    assert worker["cpus"] == "${WORKER_CPUS:-1}"
    assert worker["mem_limit"]


def test_dev_nginx_mounts_the_config_directory() -> None:
    """A single-file mount keeps serving the old file once git or an editor replaces it."""
    # Plain text: compose's !override tag isn't something yaml.safe_load can read.
    compose = COMPOSE_DEV.read_text()

    assert "- ./infra/nginx:/etc/nginx/conf.d:ro" in compose
    assert "./infra/nginx/default.conf" not in compose


def test_nginx_reload_validates_first() -> None:
    recipe = MAKEFILE.read_text().split("nginx-reload:", 1)[1]

    assert recipe.index("nginx nginx -t") < recipe.index("nginx nginx -s reload")


def test_deploy_image_serves_the_built_site() -> None:
    """Reads the build definition only; scripts/smoke.sh proves the built site is served."""
    dockerfile = (NGINX_DIR / "Dockerfile").read_text()
    nginx = yaml.safe_load(COMPOSE.read_text())["services"]["nginx"]

    assert "target" not in nginx["build"]
    assert nginx["build"]["additional_contexts"]["frontend"] == "./frontend"
    final_stage = dockerfile.rsplit("FROM ", 1)[1]
    assert "spa-prod/location.inc /etc/nginx/spa/location.inc" in final_stage
    assert "--from=spa /app/dist/ /usr/share/nginx/html/" in final_stage


def test_dev_nginx_gets_the_vite_location_from_a_directory_mount() -> None:
    nginx = _dev_service("nginx")

    assert "./infra/nginx/spa-dev:/etc/nginx/spa:ro" in nginx["volumes"]
    assert nginx["build"]["target"] == "nginx-base"


def test_spa_csp_allows_no_inline_code() -> None:
    """D57: scripts and styles come only from the site's own files. The CSP must sit where
    every page lands: unknown paths fall back to /index.html, and add_header is per location."""
    conf = (NGINX_DIR / "spa-prod" / "location.inc").read_text()
    page_location = re.search(r"location = /index\.html \{(.*?)\n\}", conf, re.DOTALL)

    assert "try_files $uri /index.html;" in conf
    assert page_location
    csp = re.search(r'add_header Content-Security-Policy "([^"]+)"', page_location[1])
    assert csp
    assert "script-src 'self';" in csp[1]
    assert "style-src 'self';" in csp[1]
    assert "frame-ancestors 'none'" in csp[1]
    assert "unsafe" not in csp[1]
