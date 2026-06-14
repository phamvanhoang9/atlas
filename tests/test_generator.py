from types import SimpleNamespace

import pytest

from src.agents.generator import _ensure_report_structure, generate_report_node


CONTEXT = [
    """### Nguồn 1: Security Considerations for Artificial Intelligence Agents
URL: https://arxiv.org/html/2603.12230v2

Agent systems require attack-surface analysis and layered controls.""",
    """### Nguồn 2: https://example.com/source-without-title
URL: https://example.com/source-without-title

Reliability should be evaluated with consistency and resilience metrics.""",
]


def test_ensure_report_structure_links_inline_citations_and_reference_titles() -> None:
    report = """# Câu hỏi

## Câu trả lời
Agent systems need layered controls [1][2].
Reliability needs repeated checks [1, 2].

## Nguồn tham khảo
[1] Security Considerations for Artificial Intelligence Agents. https://arxiv.org/html/2603.12230v2
[2] https://example.com/source-without-title
"""

    normalized = _ensure_report_structure(report, "Câu hỏi", CONTEXT)

    assert "controls [[1]](#source-1)[[2]](#source-2)." in normalized
    assert "checks [[1]](#source-1)[[2]](#source-2)." in normalized
    assert '- <span id="source-1" class="report-source-anchor"></span>[[1]](#source-1) [Security Considerations for Artificial Intelligence Agents](https://arxiv.org/html/2603.12230v2)' in normalized
    assert '- <span id="source-2" class="report-source-anchor"></span>[[2]](#source-2) [Document from example.com: source-without-title](https://example.com/source-without-title)' in normalized
    assert "Nguồn 2" not in normalized
    assert "Security Considerations for Artificial Intelligence Agents. https://arxiv.org" not in normalized


def test_ensure_report_structure_appends_clickable_references_for_mode_reports() -> None:
    reports = [
        "# Hỏi đáp\n\n## Bằng chứng từ nguồn\nAttack-surface analysis matters [1].",
        "# Danh sách đọc\n\n#### 1. Agent Security\n**Đóng góp chính**: Phân tích rủi ro tool-enabled agents [1].",
        "# Phân tích\n\n## Rủi ro triển khai\nSandboxing reduces execution risk [1].",
    ]

    for report in reports:
        normalized = _ensure_report_structure(report, "Agent security", CONTEXT)

        assert "[[1]](#source-1)" in normalized
        assert "## Sources" in normalized
        assert "[Security Considerations for Artificial Intelligence Agents](https://arxiv.org/html/2603.12230v2)" in normalized


def test_ensure_report_structure_recovers_sources_from_plain_reference_section() -> None:
    report = """# Chống tấn công agent web

## Câu trả lời
Mô hình hóa bề mặt tấn công giúp xác định điểm yếu trong kiến trúc agent [1].
Agentic browsers cần được kiểm tra prompt injection và social engineering [2][3].

## Nguồn tham khảo
- [1] A Systematic Survey of Security Threats and Defenses in LLM-Based AI Agents: A Layered Attack Surface Framework. https://arxiv.org/html/2604.23338v2
- [2] WAAA! Web Adversaries Against Agentic Browsers. https://arxiv.org/html/2605.05509v1
- [3] FP-Agent: Fingerprinting AI Browsing Agents. https://arxiv.org/html/2605.01247v1
"""

    normalized = _ensure_report_structure(report, "Chống tấn công agent web", [])

    assert "[[1]](#source-1)" in normalized
    assert "[[2]](#source-2)[[3]](#source-3)" in normalized
    assert '<span id="source-1" class="report-source-anchor"></span>[[1]](#source-1)' in normalized
    assert (
        "[A Systematic Survey of Security Threats and Defenses in LLM-Based AI Agents: "
        "A Layered Attack Surface Framework](https://arxiv.org/html/2604.23338v2)"
    ) in normalized
    assert "Framework. https://arxiv.org/html/2604.23338v2" not in normalized


def test_ensure_report_structure_uses_clear_reference_title_when_context_title_is_metadata() -> None:
    context = [
        """Source: https://arxiv.org/html/2604.23338v2
Title: Content: 'author': '', 'subject': '', 'keywords': '', page_content='Chhabra et al.: Agentic AI Security'
Content about agentic AI security.""",
    ]
    report = """# Agentic AI security

## Câu trả lời
Threat modeling should cover the agentic AI lifecycle [1].

## Nguồn tham khảo
- [1] Chhabra et al.: Agentic AI Security
"""

    normalized = _ensure_report_structure(report, "Agentic AI security", context)

    assert "[[1]](#source-1)" in normalized
    assert "[Chhabra et al.: Agentic AI Security](https://arxiv.org/html/2604.23338v2)" in normalized
    assert "Content: 'author'" not in normalized
    assert "Nguồn 1" not in normalized


def test_ensure_report_structure_extracts_all_sources_from_single_compressed_context() -> None:
    context = [
        """Source: https://example.com/agentic-security
Title: Agentic AI Security
Content: security overview

Source: https://example.com/threat-detection
Title: Threat Detection for AI Agents
Content: threat detection

Source: https://example.com/risk-assessment
Title: Risk Assessment for Agent Systems
Content: risk assessment

Source: https://example.com/monitoring
Title: Continuous Monitoring for Agentic Workflows
Content: monitoring

Source: https://example.com/training
Title: Security Training for Agent Operators
Content: training""",
    ]
    report = """# Phòng chống mã độc

## Câu trả lời
Agentic AI cần nguyên tắc an ninh phù hợp [1].
Phát hiện tự động giúp phản ứng nhanh [2].
Đánh giá rủi ro định kỳ giúp cập nhật phòng thủ [3].
Theo dõi hoạt động đáng ngờ giúp khắc phục kịp thời [4].
Đào tạo nhân viên giúp phản ứng đúng cách [5].

## Nguồn tham khảo
- [1] Agentic AI Security URL
- [2] Threat Detection for AI Agents URL
- [3] Risk Assessment for Agent Systems URL
- [4] Continuous Monitoring for Agentic Workflows URL
- [5] Security Training for Agent Operators URL
"""

    normalized = _ensure_report_structure(report, "Phòng chống mã độc", context)

    for index in range(1, 6):
        assert f"[[{index}]](#source-{index})" in normalized
        assert f'id="source-{index}" class="report-source-anchor"' in normalized

    assert normalized.count('class="report-source-anchor"') == 5
    assert "[Agentic AI Security](https://example.com/agentic-security)" in normalized
    assert "[Threat Detection for AI Agents](https://example.com/threat-detection)" in normalized
    assert "[Risk Assessment for Agent Systems](https://example.com/risk-assessment)" in normalized
    assert "[Continuous Monitoring for Agentic Workflows](https://example.com/monitoring)" in normalized
    assert "[Security Training for Agent Operators](https://example.com/training)" in normalized
    assert " URL" not in normalized
    assert "https://example.com/" not in normalized.split("## Nguồn tham khảo", maxsplit=1)[0]


def test_ensure_report_structure_strips_parentheses_around_url_in_references() -> None:
    """LLM sometimes writes '[1] Title (https://url.com)' — the '(' must not appear in the title."""
    context = [
        """Source: https://arxiv.org/abs/2412.01024
Title: A Comprehensive Survey of Agents for Computer Use: Foundations, Challenges, and Future Directions
Content: survey content""",
        """Source: https://arxiv.org/abs/2501.00001
Title: Efficient Benchmarking of AI Agents
Content: benchmark content""",
    ]
    report = """# Survey

## Câu trả lời
Agents are evolving rapidly [1][2].

## Nguồn tham khảo
- [1] A Comprehensive Survey of Agents for Computer Use: Foundations, Challenges, and Future Directions (https://arxiv.org/abs/2412.01024)
- [2] Efficient Benchmarking of AI Agents (https://arxiv.org/abs/2501.00001)
"""

    normalized = _ensure_report_structure(report, "Survey", context)

    assert "Directions (" not in normalized
    assert "Agents (" not in normalized
    assert "[A Comprehensive Survey of Agents for Computer Use: Foundations, Challenges, and Future Directions](https://arxiv.org/abs/2412.01024)" in normalized
    assert "[Efficient Benchmarking of AI Agents](https://arxiv.org/abs/2501.00001)" in normalized


@pytest.mark.asyncio
async def test_generate_report_node_sends_final_normalized_replacement(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.messages: list[dict[str, object]] = []

        async def send_json(self, payload: dict[str, object]) -> None:
            self.messages.append(payload)

    async def fake_create_chat_completion(**kwargs: object) -> str:
        assert kwargs["websocket"] is None
        return """# Agent web security

## Câu trả lời
Agentic browsers need prompt-injection checks [1].

## Nguồn tham khảo
- [1] WAAA! Web Adversaries Against Agentic Browsers. https://arxiv.org/html/2605.05509v1
"""

    monkeypatch.setattr("src.agents.generator.create_chat_completion", fake_create_chat_completion)
    websocket = FakeWebSocket()
    cfg = SimpleNamespace(
        agent_role=None,
        llm_model="test-model",
        llm_provider="openai",
        report_format="markdown",
        total_words=100,
        temperature=0.0,
        token_limit=500,
        llm_kwargs={},
    )
    state = {
        "query": "Agent web security",
        "report_type": "hỏi đáp",
        "source_urls": [],
        "agent": "researcher",
        "agent_role": "Researcher",
        "sub_queries": [],
        "current_query_index": 0,
        "search_results": [],
        "scraped_content": [],
        "context": ["Context without source metadata but enough to generate a report."],
        "visited_urls": [],
        "report": "",
        "cfg": cfg,
        "websocket": websocket,
        "memory": None,
    }

    result = await generate_report_node(state)  # type: ignore[arg-type]

    replacement_reports = [
        message for message in websocket.messages if message.get("type") == "report" and message.get("replace") is True
    ]
    assert replacement_reports
    final_report = str(replacement_reports[-1]["output"])
    assert "[[1]](#source-1)" in final_report
    assert "[WAAA! Web Adversaries Against Agentic Browsers](https://arxiv.org/html/2605.05509v1)" in final_report
    assert "Browsers. https://arxiv.org/html/2605.05509v1" not in final_report
    assert result["report"] == final_report
