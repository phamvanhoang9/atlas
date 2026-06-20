"""Helpers for resolving configuration values across layered sources."""


def resolve(value, cfg, key: str, default):
    """Resolve a configuration value with priority.

    Priority order: passed-in ``value``, then the ``cfg`` object's
    attribute named ``key``, then ``default``.

    Args:
      value: An explicitly passed value; used as-is if not ``None``.
      cfg: A config object to look up ``key`` on.
      key: Attribute name to read from ``cfg``.
      default: Fallback value if ``cfg`` lacks ``key``.

    Returns:
      The resolved value.
    """
    return value if value is not None else getattr(cfg, key, default)