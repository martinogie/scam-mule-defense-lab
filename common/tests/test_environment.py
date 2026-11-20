"""The environment switch must never guess, and dev/ci must never be able to write prod."""

from __future__ import annotations

import pytest

from common import environment as e


@pytest.mark.parametrize("name", ["dev", "ci", "prod"])
def test_each_environment_is_recognised(name: str) -> None:
    assert e.current({e.ENV_VAR: name}).name == name


def test_surrounding_spaces_are_ignored() -> None:
    assert e.current({e.ENV_VAR: " dev "}).name == "dev"


@pytest.mark.parametrize(
    "environ", [{}, {e.ENV_VAR: ""}, {e.ENV_VAR: "production"}, {e.ENV_VAR: "DEV"}]
)
def test_missing_or_unknown_environment_stops(environ: dict[str, str]) -> None:
    with pytest.raises(e.EnvironmentNotSet, match="deliberately no default"):
        e.current(environ)


def test_reads_the_real_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(e.ENV_VAR, "ci")
    assert e.current().name == "ci"


def test_no_two_environments_share_a_name() -> None:
    """Different databases, topics and keys are what keep dev and prod apart."""
    for field in ("postgres_database", "topic_prefix", "redis_key_prefix"):
        values = [getattr(s, field) for s in e.SETTINGS.values()]
        assert len(set(values)) == len(values), field


def test_topic_and_key_names_carry_the_environment() -> None:
    dev = e.SETTINGS["dev"]
    assert dev.topic("payments") == "dev.payments"
    assert dev.redis_key("customer", "42") == "dev:customer:42"
    assert e.SETTINGS["prod"].topic("payments") == "prod.payments"


@pytest.mark.parametrize("name", ["dev", "ci"])
def test_non_prod_may_not_write_prod(name: str) -> None:
    with pytest.raises(e.ProdWriteRefused, match="only prod may"):
        e.require_prod_write(e.SETTINGS[name], "promote a model")


def test_prod_may_write_prod() -> None:
    e.require_prod_write(e.SETTINGS["prod"], "promote a model")  # no error


@pytest.mark.parametrize("value", [None, "", "change-me", " Password "])
def test_prod_refuses_placeholder_secrets(value: str | None) -> None:
    with pytest.raises(e.PlaceholderSecret) as info:
        e.check_secret(e.SETTINGS["prod"], "POSTGRES_PASSWORD", value)
    assert "POSTGRES_PASSWORD" in str(info.value)


def test_secret_value_never_appears_in_the_error() -> None:
    with pytest.raises(e.PlaceholderSecret) as info:
        e.check_secret(e.SETTINGS["prod"], "POSTGRES_PASSWORD", "change-me")
    assert "change-me" not in str(info.value)


def test_prod_accepts_a_real_secret() -> None:
    e.check_secret(e.SETTINGS["prod"], "POSTGRES_PASSWORD", "a-long-random-value")


@pytest.mark.parametrize("name", ["dev", "ci"])
def test_dev_and_ci_accept_throwaway_secrets(name: str) -> None:
    e.check_secret(e.SETTINGS[name], "POSTGRES_PASSWORD", "change-me")
