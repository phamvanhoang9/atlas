"""Shared, LLM-free building blocks for the evaluation metrics.

Provides text normalization (tokenize/strip_accents), lexical similarity and
coverage scoring used as fallbacks when no LLM judge is configured, claim
extraction for faithfulness checks, JSON parsing of judge responses, and the
DCG helper used by ranking metrics. Higher-level metric functions in
generation_metrics.py and retrieval_metrics.py build on these primitives.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from src.prompts.registry import render_prompt


JudgeCallable = Callable[[str], Awaitable[str] | str]

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "cua",
    "do",
    "for",
    "from",
    "in",
    "is",
    "la",
    "of",
    "on",
    "or",
    "the",
    "to",
    "trong",
    "va",
    "ve",
    "voi",
}


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Clamp a value to the [minimum, maximum] range."""
    return max(minimum, min(maximum, value))


def label_from_score(score: float | None, pass_threshold: float, warn_threshold: float | None = None) -> str:
    """Map a numeric score to a "pass"/"warn"/"fail"/"skipped" label.

    Args:
      score: The metric score to label, or None if the metric was not computed.
      pass_threshold: Minimum score for a "pass" label.
      warn_threshold: Minimum score for a "warn" label. Defaults to 85% of
        pass_threshold when omitted.

    Returns:
      "skipped" if score is None, otherwise "pass", "warn", or "fail".
    """
    if score is None:
        return "skipped"
    warn = warn_threshold if warn_threshold is not None else pass_threshold * 0.85
    if score >= pass_threshold:
        return "pass"
    if score >= warn:
        return "warn"
    return "fail"


def normalize_label(value: Any, fallback: str) -> str:
    """Coerce an arbitrary judge-supplied label into a known MetricLabel value.

    Args:
      value: The raw label value (e.g. from an LLM judge's JSON response).
      fallback: The label to use when value isn't a recognized label string.

    Returns:
      One of "pass", "warn", "fail", "skipped", or fallback.
    """
    label = str(value or "").strip().lower()
    return label if label in {"pass", "warn", "fail", "skipped"} else fallback


def tokenize(text: str) -> list[str]:
    """Lowercase, strip accents, and split text into tokens, dropping stopwords and single chars."""
    tokens = re.findall(r"[\w]+", strip_accents(text.lower()), flags=re.UNICODE)
    return [token for token in tokens if len(token) > 1 and token not in _STOPWORDS]


def strip_accents(text: str) -> str:
    """Replace Vietnamese accented characters with their unaccented ASCII equivalents."""
    replacements = {
        "à": "a",
        "á": "a",
        "ả": "a",
        "ã": "a",
        "ạ": "a",
        "ă": "a",
        "ằ": "a",
        "ắ": "a",
        "ẳ": "a",
        "ẵ": "a",
        "ặ": "a",
        "â": "a",
        "ầ": "a",
        "ấ": "a",
        "ẩ": "a",
        "ẫ": "a",
        "ậ": "a",
        "đ": "d",
        "è": "e",
        "é": "e",
        "ẻ": "e",
        "ẽ": "e",
        "ẹ": "e",
        "ê": "e",
        "ề": "e",
        "ế": "e",
        "ể": "e",
        "ễ": "e",
        "ệ": "e",
        "ì": "i",
        "í": "i",
        "ỉ": "i",
        "ĩ": "i",
        "ị": "i",
        "ò": "o",
        "ó": "o",
        "ỏ": "o",
        "õ": "o",
        "ọ": "o",
        "ô": "o",
        "ồ": "o",
        "ố": "o",
        "ổ": "o",
        "ỗ": "o",
        "ộ": "o",
        "ơ": "o",
        "ờ": "o",
        "ớ": "o",
        "ở": "o",
        "ỡ": "o",
        "ợ": "o",
        "ù": "u",
        "ú": "u",
        "ủ": "u",
        "ũ": "u",
        "ụ": "u",
        "ư": "u",
        "ừ": "u",
        "ứ": "u",
        "ử": "u",
        "ữ": "u",
        "ự": "u",
        "ỳ": "y",
        "ý": "y",
        "ỷ": "y",
        "ỹ": "y",
        "ỵ": "y",
    }
    return "".join(replacements.get(char, char) for char in text)


def lexical_similarity(left: str, right: str) -> float:
    """Compute token-set F1 similarity between two texts (order-insensitive)."""
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens.intersection(right_tokens))
    precision = overlap / len(left_tokens)
    recall = overlap / len(right_tokens)
    if precision + recall == 0:
        return 0.0
    return round((2 * precision * recall) / (precision + recall), 4)


def max_similarity(text: str, candidates: Sequence[str]) -> float:
    """Return the highest lexical_similarity between text and any candidate, or 0.0 if none."""
    if not candidates:
        return 0.0
    return max(lexical_similarity(text, candidate) for candidate in candidates)


def query_coverage(query: str, context: str) -> float:
    """Fraction of query tokens that appear in the context (query-side recall).

    Unlike lexical_similarity (F1), this is not penalised by a long context,
    making it suitable for checking whether a document is on-topic for a query.
    """
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    context_tokens = set(tokenize(context))
    return len(query_tokens & context_tokens) / len(query_tokens)


_ENG_STOPWORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "has", "had", "him", "his", "how", "its", "may", "our", "out",
    "was", "who", "will", "with", "that", "this", "from", "they",
    "have", "been", "were", "more", "also", "than", "when", "used",
    "uses", "which", "their", "these", "those", "would", "could", "should",
})


def bilingual_query_coverage(query: str, context: str, threshold: float = 0.20) -> float:
    """query_coverage with an English-term fallback for Vietnamese queries.

    Vietnamese queries against English sources get near-zero query_coverage
    because query tokens are in Vietnamese.  When coverage is below
    `threshold`, extract English terms (≥ 3 chars) from the query and check
    if any appear as substrings in the context; ≥ 50 % match → relevant.
    Using 3-char minimum catches short acronyms like "LLM".
    """
    score = query_coverage(query, context)
    if score >= threshold:
        return score
    eng_terms = [
        t.lower() for t in re.findall(r"[a-zA-Z]{3,}", query)
        if t.lower() not in _ENG_STOPWORDS
    ]
    if not eng_terms:
        return score
    context_lower = context.lower()
    matched = sum(1 for t in eng_terms if t in context_lower)
    if matched / len(eng_terms) >= 0.5:
        return threshold  # treat as just-relevant
    return score


def split_sentences(text: str) -> list[str]:
    """Split text into sentences on sentence-ending punctuation or newlines."""
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", normalized)
    return [part.strip(" -\t") for part in parts if part.strip(" -\t")]


def is_information_claim(sentence: str) -> bool:
    """Check whether a sentence states factual information rather than social/filler text.

    Short sentences, and sentences matching common conversational markers
    (greetings, thanks, offers to help), are excluded.
    """
    stripped = sentence.strip()
    if len(stripped) < 24:
        return False
    lower = strip_accents(stripped.lower())
    social_markers = (
        "cam on",
        "xin chao",
        "hy vong",
        "toi co the giup",
        "ban co muon",
        "would you like",
        "let me know",
        "thanks",
    )
    if any(marker in lower for marker in social_markers):
        return False
    tokens = tokenize(stripped)
    return len(tokens) >= 5 or (len(tokens) >= 4 and bool(re.search(r"\d", stripped)))


def extract_information_claims(response: str) -> list[str]:
    """Split a response into sentences and return only those that state factual claims.

    Markdown heading markers are stripped before the factual-claim check.
    """
    claims: list[str] = []
    for sentence in split_sentences(response):
        sentence = re.sub(r"^#+\s*", "", sentence).strip()
        if is_information_claim(sentence):
            claims.append(sentence)
    return claims


def parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object out of raw LLM judge output, tolerating code fences and extra text.

    Strips ```json fences if present; if direct parsing fails, falls back to
    extracting the substring between the first "{" and the last "}".

    Args:
      raw: The raw text returned by the judge LLM.

    Returns:
      The parsed JSON object as a dict.

    Raises:
      json.JSONDecodeError: If no valid JSON object could be extracted.
      ValueError: If the parsed JSON value is not an object.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Judge response must be a JSON object")
    return parsed


async def maybe_call_judge(judge: JudgeCallable | None, prompt: str) -> dict[str, Any] | None:
    """Call the judge callable with prompt and parse its JSON reply, if a judge is configured.

    Args:
      judge: A sync or async callable that returns the judge's raw text response,
        or None if no LLM judge is configured.
      prompt: The prompt to send to the judge.

    Returns:
      The parsed JSON response dict, or None if no judge was given or the
      response could not be parsed as a JSON object.
    """
    if judge is None:
        return None
    raw = judge(prompt)
    if hasattr(raw, "__await__"):
        raw = await raw  # type: ignore[assignment]
    try:
        return parse_json_object(str(raw))
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def build_judge_prompt(
    *,
    task: str,
    query: str,
    response: str = "",
    contexts: Sequence[str] | None = None,
    claims: Sequence[str] | None = None,
) -> str:
    """Render the LLM-judge prompt for a given evaluation task.

    Uses the "evaluation_judge" prompt template when available, falling back
    to a minimal inline prompt if the template registry returns None.

    Args:
      task: A short description of what the judge should score.
      query: The user query being evaluated.
      response: The generated response to judge, if applicable.
      contexts: Retrieved context texts to include, if applicable.
      claims: Extracted factual claims to include, if applicable.

    Returns:
      The fully rendered prompt string to send to the judge LLM.
    """
    prompt = render_prompt(
        "evaluation_judge",
        {
            "task": task,
            "query": query,
            "response": response,
            "contexts": "\n\n".join(contexts or []),
            "claims": "\n".join(f"- {claim}" for claim in claims or []),
        },
    )
    if prompt is not None:
        return prompt

    return (
        "Return only strict JSON with keys score, label, reason, evidence.\n"
        f"Task: {task}\nQuery: {query}\nResponse: {response}\n"
        f"Contexts:\n{chr(10).join(contexts or [])}\nClaims:\n{chr(10).join(claims or [])}"
    )


def dcg(scores: Sequence[float]) -> float:
    """Compute discounted cumulative gain over a ranked sequence of relevance scores."""
    return sum(score / math.log2(index + 2) for index, score in enumerate(scores))
