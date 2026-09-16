"""Environment selection and its enforcement.

This module implements R-11.1.a, which is one of the eight non-negotiables in
MASTER_SPEC §3. The rule exists because the most likely way this project loses
money is not a subtle modelling error -- it is a process that was believed to be
running against the paper account and was not.

Accordingly this module has no dependencies beyond the standard library, does no
I/O, and is imported before anything else in every entrypoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "AlpacaEnv",
    "ConfigurationError",
    "EnvironmentConfig",
    "load_environment_config",
    "require_alpaca_env",
]

# R-11.1.c: the live confirmation token. Deliberately awkward to type by accident.
LIVE_CONFIRMATION_TOKEN: Final = "yes-i-mean-it"

# §20.9: live trading is Phase 8. Anything earlier may not select the live environment.
LIVE_MIN_PHASE: Final = 8

_PAPER_BASE_URL: Final = "https://paper-api.alpaca.markets"
_LIVE_BASE_URL: Final = "https://api.alpaca.markets"

_SPEC: Final = "See docs/MASTER_SPEC.md §11.1."


class ConfigurationError(RuntimeError):
    """Raised when the process is not safe to start.

    Every raise site in this module is a condition under which continuing could
    place an order against the wrong account. There is no recovery path and no
    caller is expected to catch this: entrypoints let it terminate the process.
    """


class AlpacaEnv(StrEnum):
    """Which brokerage account this process trades.

    There are exactly two and there is no default (R-3.1.b).
    """

    PAPER = "paper"
    LIVE = "live"

    @property
    def is_live(self) -> bool:
        return self is AlpacaEnv.LIVE


def require_alpaca_env() -> AlpacaEnv:
    """Return the configured environment, or raise.

    R-11.1.a: ``ALPACA_ENV`` must be explicitly ``paper`` or ``live``. A missing,
    empty, or unrecognised value raises before any network call, any database
    connection, and any scheduler registration.

    Note the absence of ``.strip()`` and ``.lower()``. A value of ``" Live "``
    means someone's deployment configuration is not what they think it is, and
    quietly repairing it hides that. The failure is the useful outcome.
    """
    raw = os.environ.get("ALPACA_ENV")
    if raw is None:
        raise ConfigurationError(
            f"ALPACA_ENV is not set. It must be explicitly 'paper' or 'live'; "
            f"there is no default. {_SPEC}"
        )
    if raw not in tuple(AlpacaEnv):
        raise ConfigurationError(
            f"ALPACA_ENV must be exactly 'paper' or 'live', got {raw!r}. "
            f"Values are not trimmed or case-folded: if this looks correct, check for "
            f"whitespace or capitalisation in the deployment config. {_SPEC}"
        )
    return AlpacaEnv(raw)


def _require_phase() -> int:
    """Return ``ATLAS_PHASE``, or raise.

    The phase marker is what makes R-11.1.c enforceable: a repository that has
    only reached Phase 3 cannot select the live environment even if someone sets
    every other variable correctly.
    """
    raw = os.environ.get("ATLAS_PHASE")
    if raw is None:
        raise ConfigurationError(f"ATLAS_PHASE is not set. Expected an integer 0-8. {_SPEC}")
    try:
        phase = int(raw)
    except ValueError as exc:
        raise ConfigurationError(
            f"ATLAS_PHASE must be an integer 0-8, got {raw!r}. {_SPEC}"
        ) from exc
    if not 0 <= phase <= 8:
        raise ConfigurationError(f"ATLAS_PHASE must be between 0 and 8, got {phase}. {_SPEC}")
    return phase


def _assert_live_is_permitted(phase: int) -> None:
    """Gate the live environment behind Phase 8 and an explicit confirmation.

    R-11.1.c. The model-promotion half of that rule is enforced by the engine at
    startup once the registry exists (Phase 4); it cannot be checked here because
    this module does no I/O.
    """
    if phase < LIVE_MIN_PHASE:
        raise ConfigurationError(
            f"ALPACA_ENV=live requires ATLAS_PHASE >= {LIVE_MIN_PHASE}, got {phase}. "
            f"Live trading is Phase 8, behind the eight gates in §20.9. {_SPEC}"
        )
    confirmation = os.environ.get("ATLAS_LIVE_CONFIRMED")
    if confirmation != LIVE_CONFIRMATION_TOKEN:
        raise ConfigurationError(
            f"ALPACA_ENV=live requires ATLAS_LIVE_CONFIRMED={LIVE_CONFIRMATION_TOKEN!r}, "
            f"got {confirmation!r}. {_SPEC}"
        )


@dataclass(frozen=True, slots=True)
class EnvironmentConfig:
    """Everything derived from ``ALPACA_ENV``, resolved in exactly one place.

    R-11.1.b: it must be impossible to hold live credentials alongside a paper
    base URL. Deriving all three from one enum is how that is made structural
    rather than a thing reviewers have to notice.
    """

    env: AlpacaEnv
    phase: int
    broker_base_url: str
    credential_key_id_var: str
    credential_secret_var: str

    @property
    def is_live(self) -> bool:
        return self.env.is_live

    @property
    def label(self) -> str:
        """Upper-case tag for logs, API envelopes, and notifications (R-11.1.d)."""
        return self.env.value.upper()


def load_environment_config() -> EnvironmentConfig:
    """Resolve the environment, or raise and let the process die.

    Call this first in every entrypoint, before logging is configured, so that a
    misconfigured process produces exactly one message and a non-zero exit.
    """
    env = require_alpaca_env()
    phase = _require_phase()

    if env.is_live:
        _assert_live_is_permitted(phase)

    if env is AlpacaEnv.LIVE:
        return EnvironmentConfig(
            env=env,
            phase=phase,
            broker_base_url=_LIVE_BASE_URL,
            credential_key_id_var="ALPACA_LIVE_API_KEY_ID",
            credential_secret_var="ALPACA_LIVE_API_SECRET_KEY",
        )
    return EnvironmentConfig(
        env=env,
        phase=phase,
        broker_base_url=_PAPER_BASE_URL,
        credential_key_id_var="ALPACA_PAPER_API_KEY_ID",
        credential_secret_var="ALPACA_PAPER_API_SECRET_KEY",
    )
