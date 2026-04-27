"""Settings compatibility layer for the new config package layout."""

from src.config.config import Config, ConfigError, ConfigSchema

__all__ = ["Config", "ConfigError", "ConfigSchema"]

