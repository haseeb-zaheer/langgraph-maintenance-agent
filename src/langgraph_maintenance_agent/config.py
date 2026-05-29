"""Configuration loading and validation."""

from __future__ import annotations


class ConfigError(ValueError):
    """Raised when a maintenance agent config is invalid."""
