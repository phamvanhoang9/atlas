"""Tests for the built-in AI-native Radar watch presets."""

from src.automation.radar_presets import RADAR_PRESETS


def test_presets_have_unique_ids() -> None:
    ids = [p["id"] for p in RADAR_PRESETS]
    assert len(ids) == len(set(ids))


def test_presets_nonempty() -> None:
    assert len(RADAR_PRESETS) >= 2


def test_every_preset_has_required_fields() -> None:
    required = {
        "id", "name", "description", "topics", "mode", "cadence_unit",
        "cadence_time", "cadence_timezone", "cadence_weekday", "preferred_categories",
    }
    for preset in RADAR_PRESETS:
        assert required.issubset(preset.keys()), preset["id"]


def test_every_preset_mode_is_valid() -> None:
    for preset in RADAR_PRESETS:
        assert preset["mode"] in ("ask", "compare", "deep_dive")


def test_every_preset_cadence_is_valid() -> None:
    for preset in RADAR_PRESETS:
        assert preset["cadence_unit"] in ("daily", "weekly")
        if preset["cadence_unit"] == "weekly":
            assert preset["cadence_weekday"] in range(1, 8)
        else:
            assert preset["cadence_weekday"] is None


def test_every_preset_has_at_least_one_topic() -> None:
    for preset in RADAR_PRESETS:
        assert len(preset["topics"]) >= 1
