"""Deterministic checks for teacher-visible LLM text."""

from __future__ import annotations

import re

MAX_VISIBLE_TEXT_CHARS = 240
MAX_RATIONALE_CHARS = 600

_OFFICIAL_CLAIMS = (
    "법적 기준",
    "법적으로",
    "법정 기준 충족",
    "공식 인증",
    "공식 권장",
    "의무적으로",
)
_SAFETY_TERMS = (
    "안전교육",
    "재난대비",
    "교통안전",
    "실종유괴",
    "성폭력 예방",
    "약물 오남용",
)
_SOURCE_MARKERS = ("출처:", "근거:", "evidence_ref", "source_id")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SOURCE_ALIAS = re.compile(r"(?<![A-Za-z0-9])S\d{1,3}(?![A-Za-z0-9])")


def normalize_visible_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def visible_text_violations(
    value: str,
    *,
    max_chars: int = MAX_VISIBLE_TEXT_CHARS,
    evidence_refs: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    codes: list[str] = []
    if not value.strip():
        codes.append("BLANK_TEXT")
    if len(value) > max_chars:
        codes.append("TEXT_TOO_LONG")
    if _CONTROL.search(value):
        codes.append("CONTROL_CHARACTER")
    folded = value.casefold()
    if any(claim.casefold() in folded for claim in _OFFICIAL_CLAIMS):
        codes.append("OFFICIAL_OR_LEGAL_CLAIM")
    if any(term.casefold() in folded for term in _SAFETY_TERMS):
        codes.append("SAFETY_CONTENT_LEAKAGE")
    if any(marker.casefold() in folded for marker in _SOURCE_MARKERS):
        codes.append("SOURCE_IDENTIFIER_LEAKAGE")
    if _SOURCE_ALIAS.search(value) or any(
        ref.casefold() in folded for ref in evidence_refs
    ):
        codes.append("SOURCE_IDENTIFIER_LEAKAGE")
    return tuple(dict.fromkeys(codes))
