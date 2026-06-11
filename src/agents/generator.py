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


REFERENCE_HEADING = "## Nguồn tham khảo"
REFERENCE_HEADING_RE = re.compile(r"(?im)^#{1,6}\s*Nguồn\s+tham\s+khảo\s*$")
ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|html|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?", re.IGNORECASE)


def _extract_source_links(context: list[str]) -> list[tuple[str, str]]:
    """Extract (title, url) pairs from context, supporting both context formats.

    build_mode_context format:  ### Nguồn N: <title> / URL: <url>
    ContextCompressor format:   Source: <url> / Title: <title>
    """
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    joined = "\n---\n".join(context)

    patterns = (
        re.compile(
            r"(?ms)^###\s*Nguồn\s+\d+:\s*(?P<title>.+?)\nURL:\s*(?P<url>\S+)"
        ),
        re.compile(
            r"(?ms)^Source:\s*(?P<url>\S+)\s*\nTitle:\s*(?P<title>.*?)(?=\n(?:Source:|Content:)|\Z)"
        ),
        re.compile(r"(?m)^Source:\s*(?P<url>\S+)"),
    )

    for pattern in patterns:
        for match in pattern.finditer(joined):
            url = match.group("url").strip()
            if not url or url in seen:
                continue
            raw_title = match.groupdict().get("title", "").strip()
            title = raw_title if raw_title and raw_title != url else url
            sources.append((title, url))
            seen.add(url)
    return sources


def _split_references_section(report: str) -> tuple[str, str, str] | None:
    """Return body, heading, and tail for the references section."""
    match = REFERENCE_HEADING_RE.search(report)
    if not match:
        return None

    rest_after = report[match.end():]
    next_section = re.search(r"\n##\s+", rest_after)
    if next_section:
        tail = rest_after[next_section.start():]
    else:
        tail = ""
    return report[:match.start()], match.group(0), tail


def _extract_reference_section_sources(report: str) -> list[tuple[str, str]]:
    """Recover source titles and URLs from an LLM-written references section."""
    return [
        (title, url)
        for _, title, url in _extract_reference_section_source_map(report)
        if url
    ]


def _extract_reference_section_source_map(report: str) -> list[tuple[int, str, str]]:
    """Recover numbered source titles and optional URLs from a references section."""
    match = REFERENCE_HEADING_RE.search(report)
    if not match:
        return []

    rest_after = report[match.end():]
    next_section = re.search(r"\n##\s+", rest_after)
    references = rest_after[:next_section.start()] if next_section else rest_after

    entries: list[str] = []
    current = ""
    for line in references.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^[-*]?\s*\[+\d+\]+", stripped):
            if current:
                entries.append(current)
            current = stripped
        elif current:
            current = f"{current} {stripped}"
    if current:
        entries.append(current)

    numbered_sources: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        number_match = re.match(
            r"^[-*]?\s*\[+(?P<num>\d+)\]+(?:\]\([^)]+\))?(?:\((?P<inline_url>https?://[^)]+)\))?\s*(?P<rest>.*)$",
            entry,
        )
        if not number_match:
            continue

        source_number = int(number_match.group("num"))
        inline_url = number_match.group("inline_url")
        remainder = number_match.group("rest").strip()
        markdown_link = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", remainder)
        if markdown_link:
            title = markdown_link.group(1).strip()
            url = markdown_link.group(2).strip()
        elif inline_url:
            url = inline_url.rstrip(".,;)")
            title = remainder.strip(" .:-")
        else:
            url_match = re.search(r"https?://\S+", remainder)
            if url_match:
                url = url_match.group(0).rstrip(".,;)")
                left = re.sub(r"\s*\(\s*$", "", remainder[:url_match.start()])
                right = re.sub(r"^\s*\)\s*", "", remainder[url_match.end():])
                title = f"{left} {right}".strip(" .:-")
            else:
                url = ""
                title = remainder.strip(" .:-")

        seen_key = url or f"{source_number}:{title}"
        if seen_key in seen:
            continue
        numbered_sources.append((source_number, _clean_reference_title(title), url))
        seen.add(seen_key)

    return sorted(numbered_sources)


def _clean_reference_title(title: str) -> str:
    """Remove common citation boilerplate around an otherwise usable title."""
    cleaned = re.sub(r"\s+", " ", title or "").strip(" .:-")
    cleaned = re.sub(r"(?i)\.\s*arxiv preprint.*$", "", cleaned).strip(" .:-")
    cleaned = re.sub(r"(?i),?\s*20\d{2}\.?$", "", cleaned).strip(" .:-")
    cleaned = re.sub(r"(?i)\bURL\s*$", "", cleaned).strip(" .:-")
    return cleaned


def _fallback_title_from_url(url: str) -> str:
    """Return a clear non-raw-URL label when no usable title is available."""
    arxiv_match = ARXIV_ID_RE.search(url)
    if arxiv_match:
        return f"arXiv:{arxiv_match.group(1)}"
    host_match = re.search(r"https?://([^/]+)", url)
    if not host_match:
        return "Tài liệu tham khảo"
    host = host_match.group(1)
    path_match = re.search(r"https?://[^/]+(/[^?#]+)", url)
    if path_match:
        segment = path_match.group(1).rstrip("/").split("/")[-1]
        if segment and segment not in {"index.html", "index.htm", "index.php", "index"}:
            return f"Tài liệu từ {host}: {segment}"
    return f"Tài liệu từ {host}"


_NON_CITABLE_EXTENSIONS = {
    ".diff", ".patch", ".log", ".bin", ".exe", ".zip", ".tar", ".gz",
    ".lock", ".tmp", ".bak", ".pyc", ".whl", ".egg",
}
_HASH_SEGMENT_RE = re.compile(r"^[0-9a-f]{7,64}$", re.IGNORECASE)


def _is_citable_url(url: str) -> bool:
    """Return False for URLs that point to non-citable artifacts (diffs, blobs, hashes)."""
    if not url:
        return False
    path = url.split("?")[0].split("#")[0].rstrip("/")
    segment = path.split("/")[-1] if "/" in path else ""
    ext = re.search(r"\.[a-z0-9]+$", segment, re.IGNORECASE)
    if ext and ext.group(0).lower() in _NON_CITABLE_EXTENSIONS:
        return False
    stem = segment.split(".")[0] if "." in segment else segment
    if stem and _HASH_SEGMENT_RE.match(stem):
        return False
    return True


def _is_clear_source_title(title: str) -> bool:
    """Reject context fragments and metadata blobs as visible reference titles."""
    cleaned = title.strip()
    lower = cleaned.lower()
    if not cleaned or re.match(r"^https?://", cleaned):
        return False
    if len(cleaned) > 220:
        return False
    bad_markers = (
        "content:",
        "page_content",
        "metadata",
        "'author'",
        '"author"',
        "'subject'",
        '"subject"',
        "moddate",
        "creationdate",
    )
    if any(marker in lower for marker in bad_markers):
        return False
    if lower.startswith(("aim to ", "must ", "they ", "it ", "this ")):
        return False
    return True


def _merge_sources(context_sources: list[tuple[str, str]], report: str) -> list[tuple[str, str]]:
    """Use context URLs (authoritative) matched to LLM titles by URL, not by position."""
    # Build URL → LLM-title lookup so titles follow their actual URLs, not list order.
    url_to_ref_title: dict[str, str] = {}
    for _, title, url in _extract_reference_section_source_map(report):
        if url and url not in url_to_ref_title:
            url_to_ref_title[url] = title

    merged: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for context_title, url in context_sources:
        if not _is_citable_url(url):
            continue
        if url in seen_urls:
            continue

        reference_title = url_to_ref_title.get(url, "")
        if _is_clear_source_title(reference_title):
            title = reference_title
        elif _is_clear_source_title(context_title):
            title = _clean_reference_title(context_title)
        else:
            title = _fallback_title_from_url(url)

        # Skip entries whose display title would duplicate an already-added one.
        normalized = title.lower().strip()
        if normalized in seen_titles:
            continue

        merged.append((title, url))
        seen_urls.add(url)
        seen_titles.add(normalized)

    if merged:
        return merged

    return [
        (title if _is_clear_source_title(title) else _fallback_title_from_url(url), url)
        for _, title, url in _extract_reference_section_source_map(report)
        if url and _is_citable_url(url)
    ]


def _source_title_for_display(title: str, source_number: int) -> str:
    """Return a non-URL label for reference lists when a title is missing."""
    return title if _is_clear_source_title(title) else f"Tài liệu tham khảo {source_number}"


def _link_inline_citations(report: str, sources: list[tuple[str, str]]) -> str:
    """Convert inline numeric citation markers such as [1][2] into local anchors."""
    source_numbers = {str(index) for index, _ in enumerate(sources[:12], start=1)}

    def replace(match: re.Match[str]) -> str:
        numbers = [number.strip() for number in match.group(1).split(",")]
        linked = []
        for number in numbers:
            if number in source_numbers:
                linked.append(f"[[{number}]](#source-{number})")
            # citations beyond the actual source count are silently dropped
        return "".join(linked)

    return re.sub(r"(?<!\[)\[([0-9]+(?:\s*,\s*[0-9]+)*)\](?!\()", replace, report)


def _rebuild_references_section(report: str, sources: list[tuple[str, str]]) -> str:
    """Replace the LLM-generated ## Nguồn tham khảo block with the authoritative
    source list derived from context. Inline [N] markers in the body are re-mapped
    to the canonical numbering so they stay consistent.

    If the LLM wrote no references section, one is appended.
    """
    if not sources:
        return report

    references_section = _split_references_section(report)
    if references_section:
        body, marker, tail = references_section
    else:
        body = report
        marker = REFERENCE_HEADING
        tail = ""

    body = _link_inline_citations(body, sources)
    capped = sources[:12]
    raw_labels = [_source_title_for_display(t, n) for n, (t, _) in enumerate(capped, start=1)]
    label_counts: dict[str, int] = {}
    for lbl in raw_labels:
        label_counts[lbl] = label_counts.get(lbl, 0) + 1
    label_seen: dict[str, int] = {}
    display_titles = []
    for lbl in raw_labels:
        if label_counts[lbl] > 1:
            label_seen[lbl] = label_seen.get(lbl, 0) + 1
            display_titles.append(f"{lbl} ({label_seen[lbl]})")
        else:
            display_titles.append(lbl)

    ref_lines = "\n".join(
        f'- <span id="source-{n}" class="report-source-anchor"></span>[[{n}]](#source-{n}) '
        f'[{lbl}]({url})'
        for (n, (_, url)), lbl in zip(enumerate(capped, start=1), display_titles)
    )
    return f"{body}{marker}\n{ref_lines}{tail}"


def _ensure_report_structure(report: str, query: str, context: list[str]) -> str:
    """Ensure title exists and references section uses real titles/URLs from context."""
    normalized = report.strip()
    if not normalized.startswith("# "):
        normalized = f"# {query}\n\n{normalized}"

    sources = _merge_sources(_extract_source_links(context), normalized)
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
            websocket=None,
            max_tokens=cfg.token_limit,
            llm_kwargs=cfg.llm_kwargs,
            report_type=state["report_type"],
        )

        report = _ensure_report_structure(report, state["query"], state.get("context", []))
        if ws:
            try:
                await ws.send_json({"type": "report", "output": report, "replace": True})
            except (RuntimeError, OSError):
                pass
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
