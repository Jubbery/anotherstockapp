"""Typed configuration. See MASTER_SPEC §11 and Appendix A."""

from atlas_core.config.bootstrap import EXIT_MISCONFIGURED, bootstrap
from atlas_core.config.env import (
    AlpacaEnv,
    ConfigurationError,
    EnvironmentConfig,
    load_environment_config,
    require_alpaca_env,
)

__all__ = [
    "EXIT_MISCONFIGURED",
    "AlpacaEnv",
    "ConfigurationError",
    "EnvironmentConfig",
    "load_environment_config",
    "bootstrap",
    "require_alpaca_env",
]
