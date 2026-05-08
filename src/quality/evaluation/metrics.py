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
    return max(minimum, min(maximum, value))


def label_from_score(score: float | None, pass_threshold: float, warn_threshold: float | None = None) -> str:
    if score is None:
        return "skipped"
    warn = warn_threshold if warn_threshold is not None else pass_threshold * 0.85
    if score >= pass_threshold:
        return "pass"
    if score >= warn:
        return "warn"
    return "fail"


def normalize_label(value: Any, fallback: str) -> str:
    label = str(value or "").strip().lower()
    return label if label in {"pass", "warn", "fail", "skipped"} else fallback


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[\w]+", strip_accents(text.lower()), flags=re.UNICODE)
    return [token for token in tokens if len(token) > 1 and token not in _STOPWORDS]


def strip_accents(text: str) -> str:
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
    if not candidates:
        return 0.0
    return max(lexical_similarity(text, candidate) for candidate in candidates)


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", normalized)
    return [part.strip(" -\t") for part in parts if part.strip(" -\t")]


def is_information_claim(sentence: str) -> bool:
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
    claims: list[str] = []
    for sentence in split_sentences(response):
        sentence = re.sub(r"^#+\s*", "", sentence).strip()
        if is_information_claim(sentence):
            claims.append(sentence)
    return claims


def parse_json_object(raw: str) -> dict[str, Any]:
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
    return sum(score / math.log2(index + 2) for index, score in enumerate(scores))
