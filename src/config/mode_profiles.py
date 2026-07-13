"""Mode-specific runtime profile overrides.

Keys are canonical mode ids (``ask`` / ``compare`` / ``deep_dive``, decision
D-004, superseded 2026-07-12 — see modes_redesign_plan.md Mục 8.1 #4).
Resolution happens via ``src.modes.normalize_mode`` in
``Config.apply_mode_config``.
"""

_ASK_PROFILE = {
    "max_iterations": 1,
    "max_search_results_per_query": 6,
    "token_limit": 3000,
    "total_words": 700,
    "temperature": 0.2,
    "summary_token_limit": 1000,
    "enable_parallel_search": True,
    "similarity_threshold": 0.35,
}

_COMPARE_PROFILE = {
    # max_iterations/max_search_results_per_query sized for the job-shape
    # (comparing several objects, 2-5 in the common case per
    # modes_redesign_plan.md Mục 8.2 - not iterating deeper on one topic):
    # 4 LLM-generated sub-queries + the original = 5 total, enough room for
    # roughly one query per object plus a combined query. The per-query
    # result count is bumped over ask's (6->8) because compare's search is
    # domain-restricted to academic/primary sources (see
    # src/modes/registry.py _COMPARE_INCLUDE_DOMAINS), which narrows the
    # candidate pool per query relative to ask/deep_dive's unrestricted
    # search. max_scrape_urls=24 (registry.py) is the real cost ceiling
    # regardless of these two knobs, and the >5-object outlier case is
    # capped at the Decision Matrix layer, not by inflating this profile.
    "max_iterations": 4,
    "max_search_results_per_query": 8,
    "token_limit": 8000,
    "total_words": 2000,
    "temperature": 0.2,
    "summary_token_limit": 1000,
    "similarity_threshold": 0.45,
    "enable_parallel_search": True,
}

_DEEP_DIVE_PROFILE = {
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
    "ask": _ASK_PROFILE,
    "compare": _COMPARE_PROFILE,
    "deep_dive": _DEEP_DIVE_PROFILE,
}
