"""Built-in AI-native Radar watch presets — quick-fill templates, not stored

rows. Demo-ready cadence + preferred_categories so a user can create a
useful watch in one click instead of configuring from a blank form.
"""

from __future__ import annotations

from typing import Any

RADAR_PRESETS: list[dict[str, Any]] = [
    {
        "id": "arxiv-daily",
        "name": "arXiv daily — LLMs, diffusion, RLHF",
        "description": "New arXiv preprints in LLM research, diffusion models, and RLHF, every morning.",
        "topics": ["new arXiv papers in large language models, diffusion models, and RLHF"],
        "mode": "ask",
        "cadence_unit": "daily",
        "cadence_time": "08:00",
        "cadence_timezone": "UTC",
        "cadence_weekday": None,
        "preferred_categories": ["arxiv_preprint", "peer_reviewed"],
    },
    {
        "id": "model-release-weekly",
        "name": "Model & tool releases — weekly",
        "description": "New AI model releases, pricing changes, and benchmark results, once a week.",
        "topics": ["new AI model releases, pricing, and benchmark results"],
        "mode": "compare",
        "cadence_unit": "weekly",
        "cadence_time": "08:00",
        "cadence_timezone": "UTC",
        "cadence_weekday": 1,
        "preferred_categories": ["official", "ai_lab_blog", "github_repo"],
    },
    {
        "id": "oss-ai-weekly",
        "name": "Open-source AI — weekly",
        "description": "Notable new open-source AI repos and releases, once a week.",
        "topics": ["notable new open-source AI models, libraries, and tools on GitHub"],
        "mode": "ask",
        "cadence_unit": "weekly",
        "cadence_time": "08:00",
        "cadence_timezone": "UTC",
        "cadence_weekday": 5,
        "preferred_categories": ["github_repo", "engineering_blog"],
    },
]
