"""Generator agent — produces the final report and suggested questions."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import traceback
from typing import Any

from src.llm.completion import create_chat_completion
from src.orchestration.state import ResearchState
from src.prompts.functions import (
    generate_paper_analysis_prompt,
    generate_suggested_questions_prompt,
    generate_topic_analysis_prompt,
    get_report_by_type,
)
from src.quality import ReportValidator
from src.transport.streaming import stream_output

logger = logging.getLogger(__name__)


def _extract_source_links(context: list[str]) -> list[tuple[str, str]]:
    """Extract (title, url) pairs from context, supporting both context formats.

    build_mode_context format:  ### Nguồn N: <title> / URL: <url>
    ContextCompressor format:   Source: <url> / Title: <title>
    """
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    joined = "\n".join(context)
    blocks = re.split(r"\n---\n|\n\n---\n\n", joined)
    for block in blocks:
        # build_mode_context format
        title_match = re.search(r"^###\s*Nguồn\s+\d+:\s*(.+)$", block, flags=re.MULTILINE)
        url_match = re.search(r"^URL:\s*(\S+)", block, flags=re.MULTILINE)

        # ContextCompressor format
        if not url_match:
            url_match = re.search(r"^Source:\s*(\S+)", block, flags=re.MULTILINE)
        if not title_match:
            title_match = re.search(r"^Title:\s*(.+)$", block, flags=re.MULTILINE)

        url = url_match.group(1).strip() if url_match else ""
        if not url or url in seen:
            continue
        raw_title = title_match.group(1).strip() if title_match else ""
        title = raw_title if raw_title and raw_title != url else url
        sources.append((title, url))
        seen.add(url)
    return sources


def _rebuild_references_section(report: str, sources: list[tuple[str, str]]) -> str:
    """Replace the LLM-generated ## Nguồn tham khảo block with the authoritative
    source list derived from context. Inline [N] markers in the body are re-mapped
    to the canonical numbering so they stay consistent.

    If the LLM wrote no references section, one is appended.
    """
    if not sources:
        return report

    marker = "## Nguồn tham khảo"
    idx = report.find(marker)
    if idx != -1:
        # Find where the references section ends (next ## heading or EOF)
        rest_after = report[idx + len(marker):]
        next_section = re.search(r"\n##\s+", rest_after)
        if next_section:
            body = report[:idx]
            tail = rest_after[next_section.start():]
        else:
            body = report[:idx]
            tail = ""
    else:
        body = report
        tail = ""

    ref_lines = "\n".join(f"- [{n}] [{title}]({url})" for n, (title, url) in enumerate(sources[:12], start=1))
    return f"{body}{marker}\n{ref_lines}{tail}"


def _ensure_report_structure(report: str, query: str, context: list[str]) -> str:
    """Ensure title exists and references section uses real titles/URLs from context."""
    normalized = report.strip()
    if not normalized.startswith("# "):
        normalized = f"# {query}\n\n{normalized}"

    sources = _extract_source_links(context)
    if sources:
        normalized = _rebuild_references_section(normalized, sources)

    return normalized


async def generate_report_node(state: ResearchState) -> dict[str, Any]:
    """Generate the final research report."""
    role = state["agent_role"]
    if state["report_type"] == "custom_report" and state["cfg"].agent_role:
        role = state["cfg"].agent_role

    ws = state.get("websocket")
    context_list = state.get("context", [])
    if not context_list or all(not c for c in context_list):
        await stream_output("logs", "⚠️ Không có context để tạo báo cáo\n", ws)
        error_msg = "Không thể tạo báo cáo do thiếu thông tin context."
        if ws:
            try:
                await ws.send_json({"type": "report", "output": error_msg})
            except (RuntimeError, OSError):
                pass
        return {**state, "report": error_msg}

    ws = state.get("websocket")
    cfg = state["cfg"]
    logger.info(
        "Report generation start mode=%s query_len=%s context_items=%s context_chars=%s model=%s provider=%s",
        state["report_type"],
        len(state["query"]),
        len(context_list),
        sum(len(c) for c in context_list),
        cfg.llm_model,
        cfg.llm_provider,
    )
    await stream_output("logs", f"✍️ Đang viết {state['report_type']} cho: {state['query']}...", ws)

    try:
        has_urls = bool(state.get("source_urls"))
        is_analysis = state["report_type"] == "phân tích"

        if is_analysis:
            if has_urls:
                generate_prompt = generate_paper_analysis_prompt
                role = (
                    "Bạn là AI researcher đang đọc và giải thích chi tiết bài báo khoa học. "
                    "CHỈ sử dụng thông tin từ bài báo được cung cấp, KHÔNG dùng kiến thức training. "
                    "Hướng dẫn người đọc hiểu và triển khai ý tưởng từ bài báo."
                )
            else:
                generate_prompt = generate_topic_analysis_prompt
                role = (
                    "Bạn là AI research expert phân tích chuyên sâu một chủ đề nghiên cứu. "
                    "TẬP TRUNG TUYỆT ĐỐI vào chủ đề được hỏi, KHÔNG lan man sang chủ đề khác. "
                    "Tổng hợp insights từ nhiều papers, phân tích toàn diện và sâu sắc về chủ đề."
                )
        else:
            generate_prompt = get_report_by_type(state["report_type"])

        report = await create_chat_completion(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": role},
                {"role": "user", "content": generate_prompt(
                    state["query"],
                    state.get("context", []),
                    cfg.report_format,
                    cfg.total_words,
                )},
            ],
            temperature=cfg.temperature,
            llm_provider=cfg.llm_provider,
            stream=True,
            websocket=ws,
            max_tokens=cfg.token_limit,
            llm_kwargs=cfg.llm_kwargs,
            report_type=state["report_type"],
        )

        report = _ensure_report_structure(report, state["query"], state.get("context", []))
        quality = ReportValidator().validate(report, state.get("context", []))
        logger.info(
            "Report generation complete chars=%s quality_passed=%s warnings=%s",
            len(report),
            quality.passed,
            len(quality.warnings),
        )
        if ws:
            await stream_output("quality_check", quality.to_dict(), ws, log_to_console=False)
            msg = (
                "Đã kiểm tra chất lượng báo cáo: đạt ngưỡng.\n"
                if quality.passed
                else "Cần xem lại chất lượng báo cáo và trích dẫn.\n"
            )
            await stream_output("logs", msg, ws)

        if ws:
            await stream_output("logs", "💭 Đang tạo câu hỏi gợi ý...\n", ws)
            try:
                await asyncio.wait_for(
                    _generate_suggested_questions(state["query"], report, state["report_type"], cfg, ws),
                    timeout=12.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Suggested question generation timed out")
                await stream_output("logs", "⚠️ Tạo câu hỏi gợi ý quá lâu, bỏ qua bước này.\n", ws)

        return {**state, "report": report}

    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}"

        if any(k in error_msg for k in ("ReadError", "ConnectError", "TimeoutException")):
            user_msg = "❌ Lỗi kết nối mạng khi tạo báo cáo."
            logger.error(user_msg)
            await stream_output("logs", user_msg, ws)
        else:
            logger.error("Error generating report: %s", error_msg)

        logger.error("Traceback: %s", tb)
        error_report = f"Lỗi khi tạo báo cáo: {error_msg}. Vui lòng thử lại sau."
        if ws:
            try:
                await ws.send_json({"type": "report", "output": error_report})
            except (RuntimeError, OSError):
                pass
        return {**state, "report": error_report}


async def _generate_suggested_questions(
    query: str, report: str, report_type: str, cfg: Any, websocket: Any
) -> None:
    """Fire-and-forget: generate follow-up questions without blocking."""
    try:
        if not websocket or len(report) < 200:
            return

        prompt = generate_suggested_questions_prompt(query, report, report_type)
        raw = await create_chat_completion(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": "You are a research assistant that generates insightful follow-up questions in Vietnamese. Always return a valid JSON array."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            llm_provider=cfg.llm_provider,
            stream=False,
            websocket=None,
            max_tokens=500,
            llm_kwargs=cfg.llm_kwargs,
            report_type=report_type,
        )

        try:
            questions = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            questions = json.loads(match.group(0)) if match else None

        if isinstance(questions, list) and questions:
            logger.info("Suggested questions generated count=%s", len(questions))
            try:
                await websocket.send_json({"type": "suggested_questions", "output": questions})
                await stream_output("logs", f"✅ Đã tạo {len(questions)} câu hỏi gợi ý\n", websocket)
            except (RuntimeError, OSError):
                pass

    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        logger.error("Error generating suggested questions: %s", exc)


async def process_context_node(state: ResearchState) -> dict[str, Any]:
    """Validate collected context before report generation."""
    context = state.get("context", [])
    logger.info(
        "Process context node context_items=%s context_chars=%s",
        len(context),
        sum(len(c) for c in context),
    )
    if not context or all(not c for c in context):
        await stream_output("logs", "⚠️ Không có context để xử lý\n", state.get("websocket"))
    return state
