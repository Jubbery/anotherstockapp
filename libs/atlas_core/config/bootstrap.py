"""The first thing every entrypoint does.

R-11.1.a requires that a misconfigured process fail before any network call, any
database connection, any scheduler registration, and any log line other than the
error itself. That ordering is why this writes to ``stderr`` directly instead of
going through logging: configuring a logger is itself work, and work that happens
before the environment is known is work that might happen against the wrong
account.
"""

from __future__ import annotations

import sys
from typing import NoReturn

from atlas_core.config.env import ConfigurationError, EnvironmentConfig, load_environment_config

__all__ = ["EXIT_MISCONFIGURED", "bootstrap"]

# Distinct from 1 so an operator reading a crash loop can tell a configuration
# refusal from an ordinary unhandled exception without opening the logs.
EXIT_MISCONFIGURED = 78  # EX_CONFIG, sysexits.h


def _die(service: str, error: ConfigurationError) -> NoReturn:
    sys.stderr.write(f"FATAL [{service}] refusing to start: {error}\n")
    sys.stderr.flush()
    raise SystemExit(EXIT_MISCONFIGURED)


def bootstrap(service: str) -> EnvironmentConfig:
    """Resolve the environment or terminate the process.

    Returns the resolved config so the caller can label every log line, API
    envelope, and notification with the environment (R-11.1.d).
    """
    try:
        config = load_environment_config()
    except ConfigurationError as error:
        _die(service, error)

    sys.stderr.write(
        f"[{service}] environment={config.label} phase={config.phase} "
        f"broker={config.broker_base_url}\n"
    )
    return config
