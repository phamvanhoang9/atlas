"""Mode-specific runtime profile overrides."""

MODE_CONFIGS = {
    "hỏi đáp": {
        "max_iterations": 1,
        "max_search_results_per_query": 3,
        "token_limit": 3000,
        "total_words": 700,
        "temperature": 0.2,
        "summary_token_limit": 500,
        "enable_parallel_search": True,
    },
    "đề xuất bài báo": {
        "max_iterations": 3,
        "max_search_results_per_query": 7,
        "token_limit": 8000,
        "total_words": 2000,
        "temperature": 0.3,
        "summary_token_limit": 1000,
        "enable_parallel_search": True,
    },
    "phân tích": {
        "max_iterations": 5,
        "max_search_results_per_query": 7,
        "token_limit": 12000,
        "total_words": 3000,
        "temperature": 0.3,
        "summary_token_limit": 1200,
        "enable_parallel_search": True,
    },
}

