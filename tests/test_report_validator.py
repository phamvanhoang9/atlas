"""Tests for `ReportValidator`: grounding checks on generated report citations.

Verifies citation URLs in a report are matched against the source context
(Vietnamese-language report fixtures, matching the product's UI locale).
"""

from src.quality import ReportValidator


def test_report_validator_passes_grounded_report() -> None:
    context = ["Source: https://example.com/paper\nContent: reliable context"]
    report = "Bao cao day du " * 80 + "Nguon: https://example.com/paper"

    quality = ReportValidator().validate(report, context)

    assert quality.passed
    assert quality.grounded_url_count == 1


def test_report_validator_warns_on_ungrounded_url() -> None:
    context = ["Source: https://example.com/paper\nContent: reliable context"]
    report = "Bao cao day du " * 80 + "Nguon: https://other.example/paper"

    quality = ReportValidator().validate(report, context)

    assert not quality.passed
    assert any("khong xuat hien" in warning for warning in quality.warnings)
