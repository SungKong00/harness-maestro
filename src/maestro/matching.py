from __future__ import annotations

import re
from collections.abc import Iterable

TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[가-힣]+", re.IGNORECASE)
KOREAN_SUFFIXES = (
    "해주세요",
    "합니다",
    "해줘",
    "해서",
    "해도",
    "해야",
    "했다",
    "하지",
    "하기",
    "하고",
    "하면",
    "하는",
    "하다",
    "에서",
    "으로",
    "부터",
    "까지",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "로",
    "와",
    "과",
    "도",
    "만",
)


def token_variants(token: str) -> frozenset[str]:
    folded = token.casefold()
    variants = {folded}
    if len(folded) < 3 or not re.fullmatch(r"[가-힣]+", folded):
        return frozenset(variants)
    for suffix in KOREAN_SUFFIXES:
        if folded.endswith(suffix):
            stem = folded[: -len(suffix)]
            if len(stem) >= 2:
                variants.add(stem)
            break
    return frozenset(variants)


def searchable_terms(
    text: str,
    stopwords: Iterable[str] = (),
) -> frozenset[str]:
    excluded = {item.casefold() for item in stopwords}
    terms: set[str] = set()
    for token in TOKEN_PATTERN.findall(text):
        terms.update(
            variant
            for variant in token_variants(token)
            if len(variant) > 1 and variant not in excluded
        )
    return frozenset(terms)


def term_matches(terms: frozenset[str] | set[str], term: str) -> bool:
    tokens = TOKEN_PATTERN.findall(term)
    if not tokens:
        return False
    return all(bool(token_variants(token).intersection(terms)) for token in tokens)
