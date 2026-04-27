
def resolve(value, cfg, key: str, default):
    """
    Resolve a configuration value with priority:
    1. passed value
    2. config object attribute
    3. fallback default
    """
    return value if value is not None else getattr(cfg, key, default)