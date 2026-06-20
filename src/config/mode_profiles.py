"""Mode-specific runtime profile overrides.

Keys are canonical mode ids (``quick`` / ``research`` / ``deep``, decision
D-004). Resolution happens via ``src.modes.normalize_mode`` in
``Config.apply_mode_config``.
"""

_QUICK_PROFILE = {
    "max_iterations": 1,
    "max_search_results_per_query": 6,
    "token_limit": 3000,
    "total_words": 700,
    "temperature": 0.2,
    "summary_token_limit": 1000,
    "enable_parallel_search": True,
    "similarity_threshold": 0.35,
}

_RESEARCH_PROFILE = {
    "max_iterations": 3,
    "max_search_results_per_query": 7,
    "token_limit": 8000,
    "total_words": 2000,
    "temperature": 0.2,
    "summary_token_limit": 1000,
    "similarity_threshold": 0.45,
    "enable_parallel_search": True,
}

_DEEP_PROFILE = {
    "max_iterations": 5,
    "max_search_results_per_query": 7,
    "token_limit": 12000,
    "total_words": 3000,
    "temperature": 0.2,
    "summary_token_limit": 1200,
    "similarity_threshold": 0.45,
    "enable_parallel_search": True,
}

MODE_CONFIGS = {
    "quick": _QUICK_PROFILE,
    "research": _RESEARCH_PROFILE,
    "deep": _DEEP_PROFILE,
}
