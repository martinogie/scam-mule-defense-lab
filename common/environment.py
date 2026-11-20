"""Which environment this process runs in (dev, ci or prod), and what that environment may touch.

Same pattern as the Bank Health project: every component reads SCAM_MULE_ENV through this module.
There is no default. If SCAM_MULE_ENV is missing or not exactly dev, ci or prod, everything stops
with a clear error instead of guessing (guessing wrong could mean dev writing into prod).

| env  | where it runs              | PostgreSQL database | topic / key prefix | may write prod |
|------|----------------------------|---------------------|--------------------|----------------|
| prod | the Oracle VM (demo)       | scam_mule           | prod.              | yes            |
| dev  | Martins' PC                | scam_mule_dev       | dev.               | no             |
| ci   | GitHub Actions (throwaway) | scam_mule_ci        | ci.                | no             |

The different names mean dev and prod can never read or overwrite each other's data by accident,
even if they were pointed at the same server.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

ENV_VAR = "SCAM_MULE_ENV"
ENVIRONMENTS = ("dev", "ci", "prod")

# Values that are obviously not real secrets (the ones in .env.example). Prod refuses them.
PLACEHOLDER_SECRETS = frozenset(
    {"", "change-me", "changeme", "password", "postgres", "placeholder"}
)


class EnvironmentNotSet(RuntimeError):
    """SCAM_MULE_ENV is missing or not one of dev, ci, prod."""


class ProdWriteRefused(PermissionError):
    """A non-prod environment tried to write prod data, publish, or promote a model."""


class PlaceholderSecret(ValueError):
    """Prod was started with a placeholder password instead of a real one."""


@dataclass(frozen=True)
class Settings:
    """The names one environment uses. Nothing secret lives here."""

    name: str
    postgres_database: str
    topic_prefix: str  # Redpanda topics, e.g. "dev.payments"
    redis_key_prefix: str  # Redis keys, e.g. "dev:features:customer:123"

    @property
    def is_prod(self) -> bool:
        return self.name == "prod"

    def topic(self, base: str) -> str:
        """Full Redpanda topic name, e.g. topic("payments") -> "dev.payments"."""
        return f"{self.topic_prefix}{base}"

    def redis_key(self, *parts: str) -> str:
        """Full Redis key, e.g. redis_key("customer", "42") -> "dev:customer:42"."""
        return self.redis_key_prefix + ":".join(parts)


SETTINGS: dict[str, Settings] = {
    "prod": Settings("prod", "scam_mule", "prod.", "prod:"),
    "dev": Settings("dev", "scam_mule_dev", "dev.", "dev:"),
    "ci": Settings("ci", "scam_mule_ci", "ci.", "ci:"),
}


def current(environ: Mapping[str, str] | None = None) -> Settings:
    """Return the settings for SCAM_MULE_ENV, or stop if it is missing or unknown."""
    env = os.environ if environ is None else environ
    name = env.get(ENV_VAR, "").strip()
    if name not in ENVIRONMENTS:
        shown = repr(name) if name else "not set"
        raise EnvironmentNotSet(
            f"{ENV_VAR} is {shown}. Set it to one of {', '.join(ENVIRONMENTS)} "
            "(in .env on your machine, or in the CI workflow). There is deliberately no default."
        )
    return SETTINGS[name]


def require_prod_write(settings: Settings, what: str) -> None:
    """Call before anything that writes prod data, publishes, or promotes a model."""
    if not settings.is_prod:
        raise ProdWriteRefused(f"{settings.name} may not {what}; only prod may.")


def check_secret(settings: Settings, name: str, value: str | None) -> None:
    """In prod, refuse a missing or placeholder secret. Dev and CI may use throwaway values.

    Only the secret's NAME appears in the error, never its value.
    """
    if settings.is_prod and (value or "").strip().lower() in PLACEHOLDER_SECRETS:
        raise PlaceholderSecret(
            f"{name} is missing or still a placeholder. Set a real value in the prod .env."
        )
