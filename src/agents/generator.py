"""Generator agent — produces the final report and suggested questions."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import traceback
from typing import Any

from src.llm.completion import create_chat_completion
from src.modes import normalize_mode
from src.orchestration.state import ResearchState
from src.prompts.functions import (
    generate_suggested_questions_prompt,
    get_report_by_type,
    system_role_for_mode,
)
from src.quality import ReportValidator
from src.transport.streaming import stream_output

logger = logging.getLogger(__name__)


REFERENCE_HEADING = "## Sources"
# Matches the canonical EN heading plus legacy headings still present in
# stored reports and older prompt outputs.
REFERENCE_HEADING_RE = re.compile(
    r"(?im)^#{1,6}\s*(?:Sources|References|Nguồn\s+tham\s+khảo)\s*$"
)
ARXIV_ID_RE = re.compile(r"arxiv\.org/(?:abs|html|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?", re.IGNORECASE)


def _extract_source_links(context: list[str]) -> list[tuple[str, str]]:
    """Extract (title, url) pairs from context, supporting both context formats.

    build_mode_context format:  ### Source N: <title> / URL: <url>  (legacy: ### Nguồn N:)
    ContextCompressor format:   Source: <url> / Title: <title>
    """
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    joined = "\n---\n".join(context)

    patterns = (
        re.compile(
            r"(?ms)^###\s*(?:Source|Nguồn)\s+\d+:\s*(?P<title>.+?)\nURL:\s*(?P<url>\S+)"
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


_SOURCE_CATEGORY_RE = re.compile(
    r"(?m)^URL:\s*(?P<url>\S+)\s*\nCategory:\s*(?P<label>.+?)\s*$"
)


def _extract_source_categories(context: list[str]) -> dict[str, str]:
    """Map source URL → quality category label parsed from context headers."""
    categories: dict[str, str] = {}
    for chunk in context:
        for match in _SOURCE_CATEGORY_RE.finditer(chunk):
            categories.setdefault(match.group("url").strip(), match.group("label").strip())
    return categories


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
        return "Reference"
    host = host_match.group(1)
    path_match = re.search(r"https?://[^/]+(/[^?#]+)", url)
    if path_match:
        segment = path_match.group(1).rstrip("/").split("/")[-1]
        if segment and segment not in {"index.html", "index.htm", "index.php", "index"}:
            return f"Document from {host}: {segment}"
    return f"Document from {host}"


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
    # References written without any URL can only be matched by their [N] number.
    url_to_ref_title: dict[str, str] = {}
    number_to_ref_title: dict[int, str] = {}
    for number, title, url in _extract_reference_section_source_map(report):
        if url:
            url_to_ref_title.setdefault(url, title)
        else:
            number_to_ref_title.setdefault(number, title)

    merged: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for context_title, url in context_sources:
        if not _is_citable_url(url):
            continue
        if url in seen_urls:
            continue

        reference_title = url_to_ref_title.get(url) or number_to_ref_title.get(len(merged) + 1, "")
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
    return title if _is_clear_source_title(title) else f"Reference {source_number}"


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


def _rebuild_references_section(
    report: str,
    sources: list[tuple[str, str]],
    source_categories: dict[str, str] | None = None,
) -> str:
    """Replace the LLM-generated references block with the authoritative
    source list derived from context. Inline [N] markers in the body are re-mapped
    to the canonical numbering so they stay consistent.

    If the LLM wrote no references section, one is appended. When a source's
    quality category is known it is shown after the link.
    """
    if not sources:
        return report
    source_categories = source_categories or {}

    references_section = _split_references_section(report)
    if references_section:
        body, marker, tail = references_section
    else:
        body = report.rstrip("\n")
        marker = f"\n\n{REFERENCE_HEADING}"
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

    def _category_suffix(url: str) -> str:
        label = source_categories.get(url, "")
        return f" — *{label}*" if label else ""

    ref_lines = "\n".join(
        f'- <span id="source-{n}" class="report-source-anchor"></span>[[{n}]](#source-{n}) '
        f'[{lbl}]({url}){_category_suffix(url)}'
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
        normalized = _rebuild_references_section(
            normalized, sources, _extract_source_categories(context)
        )

    return normalized


async def generate_report_node(state: ResearchState) -> dict[str, Any]:
    """Generate the final research report."""
    role = state["agent_role"]
    if state["report_type"] == "custom_report" and state["cfg"].agent_role:
        role = state["cfg"].agent_role

    ws = state.get("websocket")
    context_list = state.get("context", [])
    if not context_list or all(not c for c in context_list):
        await stream_output("logs", "No context available to generate a report\n", ws)
        error_msg = "Cannot generate a report: no research context was collected. Try rephrasing the query or running a deeper mode."
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
    canonical_mode = normalize_mode(state.get("report_type"))
    await stream_output("logs", f"Writing {canonical_mode} report for: {state['query']}...", ws)

    try:
        has_urls = bool(state.get("source_urls"))
        generate_prompt = get_report_by_type(state["report_type"], has_source_urls=has_urls)
        if canonical_mode == "deep":
            # Deep research uses its strict analyst role rather than the
            # LLM-selected agent persona.
            role = system_role_for_mode(state["report_type"], has_urls)

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
                "Report quality check: passed.\n"
                if quality.passed
                else "Report quality check flagged citation/grounding issues — review the sources.\n"
            )
            await stream_output("logs", msg, ws)

        if ws:
            await stream_output("logs", "Generating follow-up questions...\n", ws)
            try:
                await asyncio.wait_for(
                    _generate_suggested_questions(state["query"], report, state["report_type"], cfg, ws),
                    timeout=12.0,
                )
            except asyncio.TimeoutError:
                logger.warning("Suggested question generation timed out")
                await stream_output("logs", "Follow-up question generation timed out, skipping.\n", ws)

        return {**state, "report": report}

    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}"

        if any(k in error_msg for k in ("ReadError", "ConnectError", "TimeoutException")):
            user_msg = "Network error while generating the report."
            logger.error(user_msg)
            await stream_output("logs", user_msg, ws)
        else:
            logger.error("Error generating report: %s", error_msg)

        logger.error("Traceback: %s", tb)
        error_report = f"Report generation failed: {error_msg}. Please try again."
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
                {"role": "system", "content": "You are a research assistant that generates insightful follow-up questions in the same language as the user's query. Always return a valid JSON array."},
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
                await stream_output("logs", f"Generated {len(questions)} follow-up questions\n", websocket)
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
        await stream_output("logs", "No context collected to process\n", state.get("websocket"))
    return state
