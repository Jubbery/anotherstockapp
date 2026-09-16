"""R-11.1.a and R-11.1.c: the environment guard.

Phase 0 acceptance (§20.1) requires proof that the *process* exits non-zero when
``ALPACA_ENV`` is missing, empty, or invalid -- not merely that a function
raises. The subprocess tests below are that proof; the unit tests around them
cover the branches.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from atlas_core.config import (
    EXIT_MISCONFIGURED,
    AlpacaEnv,
    ConfigurationError,
    load_environment_config,
    require_alpaca_env,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Entrypoints that must all refuse to start. If a new deployable unit is added
# without the guard, the parametrisation here is what catches it.
ENTRYPOINTS = ["services.engine", "services.worker"]

# Every value that is not exactly "paper" or "live". The whitespace and casing
# cases matter: require_alpaca_env deliberately does not repair them.
BAD_ENV_VALUES = ["", "Paper", "PAPER", " paper", "paper ", "live ", "prod", "sandbox", "1", "none"]


def _run_module(module: str, env_overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(REPO_ROOT / "libs") + ":" + str(REPO_ROOT),
        **env_overrides,
    }
    return subprocess.run(
        [sys.executable, "-m", module],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_process_exits_nonzero_when_alpaca_env_missing(module: str) -> None:
    result = _run_module(module, {"ATLAS_PHASE": "0"})
    assert result.returncode == EXIT_MISCONFIGURED, result.stderr
    assert "ALPACA_ENV is not set" in result.stderr


@pytest.mark.parametrize("module", ENTRYPOINTS)
@pytest.mark.parametrize("bad", BAD_ENV_VALUES)
def test_process_exits_nonzero_when_alpaca_env_invalid(module: str, bad: str) -> None:
    result = _run_module(module, {"ALPACA_ENV": bad, "ATLAS_PHASE": "0"})
    assert result.returncode == EXIT_MISCONFIGURED, result.stderr
    assert "ALPACA_ENV must be exactly" in result.stderr


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_process_starts_with_paper(module: str) -> None:
    result = _run_module(module, {"ALPACA_ENV": "paper", "ATLAS_PHASE": "0"})
    assert result.returncode == 0, result.stderr
    assert "environment=PAPER" in result.stderr


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_process_refuses_live_before_phase_8(module: str) -> None:
    """R-11.1.c: live is Phase 8, and the phase marker is not advisory."""
    result = _run_module(
        module,
        {"ALPACA_ENV": "live", "ATLAS_PHASE": "0", "ATLAS_LIVE_CONFIRMED": "yes-i-mean-it"},
    )
    assert result.returncode == EXIT_MISCONFIGURED, result.stderr
    assert "ATLAS_PHASE >= 8" in result.stderr


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_process_refuses_live_without_confirmation(module: str) -> None:
    result = _run_module(module, {"ALPACA_ENV": "live", "ATLAS_PHASE": "8"})
    assert result.returncode == EXIT_MISCONFIGURED, result.stderr
    assert "ATLAS_LIVE_CONFIRMED" in result.stderr


# ----------------------------------------------------------------- unit level


def test_require_alpaca_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigurationError, match="ALPACA_ENV is not set"):
        require_alpaca_env()


@pytest.mark.parametrize("bad", BAD_ENV_VALUES)
def test_require_alpaca_env_rejects(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    monkeypatch.setenv("ALPACA_ENV", bad)
    with pytest.raises(ConfigurationError, match="must be exactly"):
        require_alpaca_env()


@pytest.mark.parametrize(
    ("value", "expected"), [("paper", AlpacaEnv.PAPER), ("live", AlpacaEnv.LIVE)]
)
def test_require_alpaca_env_accepts(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: AlpacaEnv
) -> None:
    monkeypatch.setenv("ALPACA_ENV", value)
    assert require_alpaca_env() is expected


def test_there_is_no_default() -> None:
    """The rule is 'no default', so assert the absence rather than trusting review."""
    import inspect

    from atlas_core.config import env as env_module

    source = inspect.getsource(env_module.require_alpaca_env)
    assert 'os.environ.get("ALPACA_ENV")' in source
    assert 'os.environ.get("ALPACA_ENV",' not in source, "a default was added to ALPACA_ENV"


@pytest.mark.parametrize("bad_phase", ["", "x", "-1", "9", "3.5"])
def test_phase_must_be_valid(monkeypatch: pytest.MonkeyPatch, bad_phase: str) -> None:
    monkeypatch.setenv("ALPACA_ENV", "paper")
    monkeypatch.setenv("ATLAS_PHASE", bad_phase)
    with pytest.raises(ConfigurationError, match="ATLAS_PHASE"):
        load_environment_config()


def test_phase_must_be_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_ENV", "paper")
    with pytest.raises(ConfigurationError, match="ATLAS_PHASE is not set"):
        load_environment_config()


def test_paper_derives_paper_url_and_credential_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-11.1.b: URL and credential names come from one place, together."""
    monkeypatch.setenv("ALPACA_ENV", "paper")
    monkeypatch.setenv("ATLAS_PHASE", "0")
    config = load_environment_config()
    assert config.broker_base_url == "https://paper-api.alpaca.markets"
    assert "PAPER" in config.credential_key_id_var
    assert "LIVE" not in config.credential_key_id_var
    assert config.is_live is False
    assert config.label == "PAPER"


def test_live_derives_live_url_and_credential_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_ENV", "live")
    monkeypatch.setenv("ATLAS_PHASE", "8")
    monkeypatch.setenv("ATLAS_LIVE_CONFIRMED", "yes-i-mean-it")
    config = load_environment_config()
    assert config.broker_base_url == "https://api.alpaca.markets"
    assert "LIVE" in config.credential_key_id_var
    assert "PAPER" not in config.credential_key_id_var
    assert config.is_live is True
    assert config.label == "LIVE"


def test_paper_and_live_never_share_a_credential_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-11.1.b: it must be impossible to hold live keys behind a paper URL."""
    monkeypatch.setenv("ALPACA_ENV", "paper")
    monkeypatch.setenv("ATLAS_PHASE", "0")
    paper = load_environment_config()
    monkeypatch.setenv("ALPACA_ENV", "live")
    monkeypatch.setenv("ATLAS_PHASE", "8")
    monkeypatch.setenv("ATLAS_LIVE_CONFIRMED", "yes-i-mean-it")
    live = load_environment_config()

    assert paper.broker_base_url != live.broker_base_url
    assert paper.credential_key_id_var != live.credential_key_id_var
    assert paper.credential_secret_var != live.credential_secret_var


@pytest.mark.parametrize("token", ["", "yes", "YES-I-MEAN-IT", "yes i mean it", "true"])
def test_live_confirmation_token_is_exact(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setenv("ALPACA_ENV", "live")
    monkeypatch.setenv("ATLAS_PHASE", "8")
    monkeypatch.setenv("ATLAS_LIVE_CONFIRMED", token)
    with pytest.raises(ConfigurationError, match="ATLAS_LIVE_CONFIRMED"):
        load_environment_config()
