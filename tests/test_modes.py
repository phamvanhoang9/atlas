"""Tests for the canonical mode registry."""

from unittest.mock import MagicMock, patch

from src.config.config import Config
from src.llm.router import route_model
from src.modes import (
    ASK,
    CANONICAL_MODE_IDS,
    COMPARE,
    DEEP_DIVE,
    MODES,
    get_mode_spec,
    is_known_mode,
    normalize_mode,
)


def test_canonical_modes_are_registered() -> None:
    assert CANONICAL_MODE_IDS == ("ask", "compare", "deep_dive")
    for mode_id in CANONICAL_MODE_IDS:
        assert MODES[mode_id].id == mode_id


def test_legacy_vn_mode_ids_no_longer_resolve() -> None:
    # The old Vietnamese product mode strings were retired (decision D-004);
    # they must now fall through to the default like any unknown string.
    assert normalize_mode("hỏi đáp") == COMPARE
    assert normalize_mode("đề xuất bài báo") == COMPARE
    assert normalize_mode("phân tích") == COMPARE
    assert not is_known_mode("hỏi đáp")
    assert not is_known_mode("phân tích")


def test_legacy_english_mode_ids_no_longer_resolve() -> None:
    # 2026-07-12: quick/research/deep were retired in favor of
    # ask/compare/deep_dive (decision D-004 superseded, no back-compat shim
    # kept — see modes_redesign_plan.md Mục 8.1 #4).
    assert normalize_mode("quick") == COMPARE
    assert normalize_mode("research") == COMPARE
    assert normalize_mode("deep") == COMPARE
    assert not is_known_mode("quick")
    assert not is_known_mode("research")
    assert not is_known_mode("deep")


def test_canonical_ids_normalize_to_themselves() -> None:
    for mode_id in CANONICAL_MODE_IDS:
        assert normalize_mode(mode_id) == mode_id


def test_unknown_mode_falls_back_to_default() -> None:
    assert normalize_mode("research_report") == COMPARE
    assert normalize_mode(None) == COMPARE
    assert normalize_mode("custom_report", default=ASK) == ASK


def test_is_known_mode() -> None:
    for mode_id in CANONICAL_MODE_IDS:
        assert is_known_mode(mode_id)
    assert not is_known_mode("pizza")
    assert not is_known_mode("")
    assert not is_known_mode(None)


def test_mode_specs_have_distinct_behavior() -> None:
    ask, compare, deep_dive = MODES[ASK], MODES[COMPARE], MODES[DEEP_DIVE]

    # Distinct report templates per mode.
    assert len({ask.report_template, compare.report_template, deep_dive.report_template}) == 3
    # Compare restricts to high-quality domains; ask and deep_dive search broadly.
    assert compare.search_include_domains
    assert ask.search_include_domains is None
    assert deep_dive.search_include_domains is None
    # Deep dive with provided URLs switches to source analysis.
    assert deep_dive.url_report_template == "source_analysis"
    assert deep_dive.url_report_template != deep_dive.report_template


def test_compare_uses_decision_matrix_report_template() -> None:
    assert MODES[COMPARE].report_template == "decision_matrix"
    assert MODES[COMPARE].url_report_template == "decision_matrix"


def test_get_mode_spec_falls_back_for_unknown_strings() -> None:
    assert get_mode_spec("phân tích") is MODES[COMPARE]
    assert get_mode_spec("deep_dive") is MODES[DEEP_DIVE]


def test_apply_mode_config_accepts_canonical_ids() -> None:
    with patch("os.path.exists", return_value=True), patch("builtins.open", MagicMock()):
        with patch("json.load", return_value={}):
            config = Config()

            config.apply_mode_config("ask")
            assert config.max_iterations == 1
            assert config.total_words == 700

            config.apply_mode_config("deep_dive")
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

    assert profiles["ask"] < profiles["compare"] < profiles["deep_dive"]


def test_route_model_deep_dive_upgrades_cheap_models() -> None:
    assert route_model("deep_dive", "gpt-4o-mini", "openai") == "gpt-4o"
    assert route_model("deep_dive", "gemini-1.5-flash", "google") == "gemini-1.5-pro"


def test_route_model_deep_dive_leaves_already_strong_models_unchanged() -> None:
    assert route_model("deep_dive", "gpt-4o", "openai") == "gpt-4o"
    assert route_model("deep_dive", "gemini-1.5-pro", "google") == "gemini-1.5-pro"


def test_route_model_ask_downgrades_strong_models() -> None:
    """Ask must be genuinely cheap/fast (plan finding #1: 'quick không nhanh
    ở tầng model') — force the cheap tier even if the configured default is
    the stronger model."""
    assert route_model("ask", "gpt-4o", "openai") == "gpt-4o-mini"
    assert route_model("ask", "gemini-1.5-pro", "google") == "gemini-1.5-flash"


def test_route_model_ask_leaves_already_cheap_models_unchanged() -> None:
    assert route_model("ask", "gpt-4o-mini", "openai") == "gpt-4o-mini"
    assert route_model("ask", "gemini-1.5-flash", "google") == "gemini-1.5-flash"


def test_route_model_compare_never_overrides_requested_model() -> None:
    """Compare is the middle tier: pass through whatever is configured,
    neither forcing the cheap nor the strong variant."""
    assert route_model("compare", "gpt-4o-mini", "openai") == "gpt-4o-mini"
    assert route_model("compare", "gpt-4o", "openai") == "gpt-4o"
    assert route_model("compare", "gemini-1.5-flash", "google") == "gemini-1.5-flash"
    assert route_model("compare", "gemini-1.5-pro", "google") == "gemini-1.5-pro"


def test_route_model_never_remaps_unrecognized_custom_models() -> None:
    """A user's custom/fine-tuned model id must never be silently swapped
    out for a hardcoded tier model — only recognized flash/pro/mini/4o
    strings are ever remapped."""
    assert route_model("ask", "ft:gpt-4o-mini:acme:custom", "openai") == "ft:gpt-4o-mini:acme:custom"
    assert route_model("deep_dive", "my-custom-model", "google") == "my-custom-model"


def test_route_model_unknown_mode_falls_back_to_compare_pass_through() -> None:
    assert route_model("not_a_real_mode", "gpt-4o-mini", "openai") == "gpt-4o-mini"
    assert route_model("not_a_real_mode", "gpt-4o", "openai") == "gpt-4o"


def test_route_model_explicit_override_always_wins() -> None:
    assert route_model("deep_dive", "gpt-4o-mini", "openai", override_model="o3") == "o3"
    assert route_model("ask", "gpt-4o", "openai", override_model="custom-model") == "custom-model"
