"""The Docker Compose files must keep the promises made in ADR 0004 and the security rules.

These tests read the YAML files directly, so they run without Docker. If someone later opens a
port to the network, removes a memory cap or renames a database, CI fails before it is merged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from common.environment import SETTINGS

ROOT = Path(__file__).resolve().parents[2]
PROD_FILE = ROOT / "docker-compose.yaml"
DEV_FILE = ROOT / "docker-compose.dev.yaml"

# ADR 0004: the Phase 0 data services together may use at most 3 GB of RAM on the shared VM.
STACK_MEMORY_BUDGET_MB = 3 * 1024


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def _megabytes(value: str) -> int:
    units = {"m": 1, "g": 1024}
    return int(value[:-1]) * units[value[-1].lower()]


PROD = _load(PROD_FILE)
DEV = _load(DEV_FILE)
SERVICES: dict[str, dict[str, Any]] = PROD["services"]


def test_prod_and_dev_have_different_project_names() -> None:
    """Different project names = separate containers, networks and volumes."""
    assert PROD["name"] == "scam-mule"
    assert DEV["name"] == "scam-mule-dev"


def test_database_names_match_the_python_settings() -> None:
    assert SERVICES["postgres"]["environment"]["POSTGRES_DB"] == SETTINGS["prod"].postgres_database
    dev_db = DEV["services"]["postgres"]["environment"]["POSTGRES_DB"]
    assert dev_db == SETTINGS["dev"].postgres_database


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_ports_are_published_on_localhost_only(name: str) -> None:
    """Nothing internal may be reachable from the network; only the public demo endpoint ever is."""
    for port in SERVICES[name].get("ports", []):
        assert str(port).startswith("127.0.0.1:"), f"{name} publishes {port} beyond localhost"


def test_dev_file_does_not_add_ports() -> None:
    for name, service in DEV["services"].items():
        assert "ports" not in service, f"dev override changes ports for {name}"


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_every_service_has_a_memory_cap_and_no_swap(name: str) -> None:
    service = SERVICES[name]
    assert "mem_limit" in service, f"{name} has no memory cap"
    assert service["memswap_limit"] == service["mem_limit"], f"{name} may use swap"
    assert "cpus" in service, f"{name} has no CPU cap"


def test_whole_stack_fits_the_memory_budget() -> None:
    total = sum(_megabytes(s["mem_limit"]) for s in SERVICES.values())
    assert total <= STACK_MEMORY_BUDGET_MB, (
        f"{total} MB is over the {STACK_MEMORY_BUDGET_MB} MB budget"
    )


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_every_service_has_a_health_check(name: str) -> None:
    assert "test" in SERVICES[name]["healthcheck"]


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_bank_health_comes_first(name: str) -> None:
    """Under memory or CPU pressure, the kernel picks these containers before Bank Health's."""
    assert SERVICES[name]["oom_score_adj"] > 0
    assert SERVICES[name]["cpu_shares"] < 1024  # 1024 is Docker's default priority


@pytest.mark.parametrize("name", sorted(SERVICES))
def test_images_are_pinned_to_an_exact_version(name: str) -> None:
    """e.g. redis:8.8.4-alpine or postgres:17.12-bookworm; never :latest or a bare :17."""
    image = SERVICES[name]["image"]
    assert ":" in image, f"{name} has no tag"
    tag = image.rsplit(":", 1)[-1]
    version = tag.split("-", 1)[0].lstrip("v")  # "v1.2.3" -> "1.2.3", "17.12-bookworm" -> "17.12"
    parts = version.split(".")
    assert len(parts) >= 2, f"{name} tag {tag} is not an exact version"
    assert all(p.isdigit() for p in parts), f"{name} tag {tag} is not a version number"


def test_kafka_heap_leaves_room_inside_its_container_cap() -> None:
    """Java uses memory beyond its heap, and Kafka relies on the file cache (ADR 0002).

    If the heap grew to fill the container cap, the kernel would kill Kafka under load.
    """
    kafka = SERVICES["kafka"]
    heap_opts = str(kafka["environment"]["KAFKA_HEAP_OPTS"])
    max_heap = next(opt for opt in heap_opts.split() if opt.startswith("-Xmx"))
    heap_mb = _megabytes(max_heap.removeprefix("-Xmx"))
    cap_mb = _megabytes(kafka["mem_limit"])
    assert heap_mb <= cap_mb // 2, f"Kafka heap {heap_mb} MB is over half its {cap_mb} MB cap"


def test_kafka_never_creates_topics_by_accident() -> None:
    """A typo like dev.paymnets must fail loudly, not quietly create a new, empty topic."""
    assert str(SERVICES["kafka"]["environment"]["KAFKA_AUTO_CREATE_TOPICS_ENABLE"]) == "false"


def test_secrets_are_required_not_defaulted() -> None:
    """Compose must refuse to start without a password, never fall back to a built-in one."""
    text = PROD_FILE.read_text(encoding="utf-8")
    assert "${POSTGRES_PASSWORD:?" in text
    assert "${REDIS_PASSWORD:?" in text
