"""Tests for the canonical mode registry."""

from unittest.mock import MagicMock, patch

from src.config.config import Config
from src.llm.router import route_model
from src.modes import (
    CANONICAL_MODE_IDS,
    DEEP,
    MODES,
    QUICK,
    RESEARCH,
    get_mode_spec,
    is_known_mode,
    normalize_mode,
)


def test_canonical_modes_are_registered() -> None:
    assert CANONICAL_MODE_IDS == ("quick", "research", "deep")
    for mode_id in CANONICAL_MODE_IDS:
        assert MODES[mode_id].id == mode_id


def test_legacy_vn_mode_ids_no_longer_resolve() -> None:
    # The old Vietnamese product mode strings were retired (decision D-004);
    # they must now fall through to the default like any unknown string.
    assert normalize_mode("hỏi đáp") == RESEARCH
    assert normalize_mode("đề xuất bài báo") == RESEARCH
    assert normalize_mode("phân tích") == RESEARCH
    assert not is_known_mode("hỏi đáp")
    assert not is_known_mode("phân tích")


def test_canonical_ids_normalize_to_themselves() -> None:
    for mode_id in CANONICAL_MODE_IDS:
        assert normalize_mode(mode_id) == mode_id


def test_unknown_mode_falls_back_to_default() -> None:
    assert normalize_mode("research_report") == RESEARCH
    assert normalize_mode(None) == RESEARCH
    assert normalize_mode("custom_report", default=QUICK) == QUICK


def test_is_known_mode() -> None:
    for mode_id in CANONICAL_MODE_IDS:
        assert is_known_mode(mode_id)
    assert not is_known_mode("pizza")
    assert not is_known_mode("")
    assert not is_known_mode(None)


def test_mode_specs_have_distinct_behavior() -> None:
    quick, research, deep = MODES[QUICK], MODES[RESEARCH], MODES[DEEP]

    # Distinct report templates per mode.
    assert len({quick.report_template, research.report_template, deep.report_template}) == 3
    # Research restricts to high-quality domains; quick and deep search broadly.
    assert research.search_include_domains
    assert quick.search_include_domains is None
    assert deep.search_include_domains is None
    # Deep research with provided URLs switches to source analysis.
    assert deep.url_report_template == "source_analysis"
    assert deep.url_report_template != deep.report_template


def test_get_mode_spec_falls_back_for_unknown_strings() -> None:
    assert get_mode_spec("phân tích") is MODES[RESEARCH]
    assert get_mode_spec("deep") is MODES[DEEP]


def test_apply_mode_config_accepts_canonical_ids() -> None:
    with patch("os.path.exists", return_value=True), patch("builtins.open", MagicMock()):
        with patch("json.load", return_value={}):
            config = Config()

            config.apply_mode_config("quick")
            assert config.max_iterations == 1
            assert config.total_words == 700

            config.apply_mode_config("deep")
            assert config.max_iterations == 5
            assert config.total_words == 3000


def test_mode_profiles_scale_with_depth() -> None:
    with patch("os.path.exists", return_value=True), patch("builtins.open", MagicMock()):
        with patch("json.load", return_value={}):
            config = Config()
            profiles = {}
            for mode_id in CANONICAL_MODE_IDS:
                config.apply_mode_config(mode_id)
                profiles[mode_id] = (config.max_iterations, config.token_limit, config.total_words)

    assert profiles["quick"] < profiles["research"] < profiles["deep"]


def test_route_model_upgrades_deep_mode() -> None:
    assert route_model("deep", "gpt-4o-mini", "openai") == "gpt-4o"
    assert route_model("deep", "gemini-1.5-flash", "google") == "gemini-1.5-pro"

    # Simpler modes keep the requested (cheap) model.
    assert route_model("quick", "gpt-4o-mini", "openai") == "gpt-4o-mini"
    assert route_model("research", "gpt-4o-mini", "openai") == "gpt-4o-mini"
    assert route_model("quick", "gemini-1.5-pro", "google") == "gemini-1.5-flash"

    # Explicit override always wins.
    assert route_model("deep", "gpt-4o-mini", "openai", override_model="o3") == "o3"
