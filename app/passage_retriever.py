from __future__ import annotations

"""Deterministic retrieval for the Quantitative Business Evidence Verifier.

This module is intentionally specialized for source-cited, quantitative claims in
business-performance, market-statistics, and official economic releases. It ranks
original source passages using inspectable anchors such as entity, metric, period,
value, unit/currency, direction, scope, and material qualifiers.

It does not decide a verdict. It only selects the bounded original evidence that
is sent to the downstream judge.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import pairwise

from app.review_models import EvidencePassage, ExtractedSourceDocument, SourceTextBlock


TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9&'/-]*")
NUMBER_WITH_UNIT_RE = re.compile(
    r"(?<![\w.])"
    r"(?P<currency_prefix>"
    r"(?:US|C|A|HK|S|CN)\$|RMB\u00a5|Rp\.?|[$\u20ac\u00a3\u00a5\u20b9]|"
    r"(?:USD|CAD|EUR|GBP|CNY|RMB|JPY|INR|IDR|AUD|HKD|SGD)\b"
    r")?\s*"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*"
    r"(?P<magnitude>thousand|million|billion|trillion|k|m|bn)?\s*"
    r"(?P<unit>"
    r"%|percent(?:age)?(?:\s+points?)?|basis\s+points?|bps?|"
    r"jobs?|employees?|workers?|dollars?|people|customers?|subscribers?|"
    r"users?|units?|shares?|transactions?|visits?"
    r")?\s*"
    r"(?P<currency_suffix>\b(?:USD|CAD|EUR|GBP|CNY|RMB|JPY|INR|IDR|AUD|HKD|SGD)\b)?",
    re.IGNORECASE,
)
ENTITY_RE = re.compile(r"\b[A-Z][A-Za-z0-9&-]*(?:\s+[A-Z][A-Za-z0-9&-]*)*")
MONTH_PERIOD_RE = re.compile(
    r"\b(?P<month>"
    r"January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|"
    r"Aug\.?|Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?"
    r")\s+(?:\d{1,2},\s+)?(?P<year>\d{4})\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
QUARTER_RE = re.compile(
    r"\b(?:q(?P<number>[1-4])|(?P<word>first|second|third|fourth)\s+quarter)"
    r"(?:\s+(?:of\s+)?(?P<fiscal>fy|fiscal\s+year)?\s*(?P<year>(?:19|20)\d{2}))?\b",
    re.IGNORECASE,
)
FISCAL_YEAR_RE = re.compile(r"\b(?:fy|fiscal\s+year)\s*([12]\d{3})\b", re.IGNORECASE)
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:\s+|(?=[A-Z]))")
INITIALISM_RE = re.compile(r"\b(?:[A-Z]\.){2,}")
PERIOD_SENTINEL = "\ue000"

COMMON_ABBREVIATIONS = (
    "e.g.",
    "i.e.",
    "Mr.",
    "Mrs.",
    "Ms.",
    "Dr.",
    "Prof.",
    "Inc.",
    "Ltd.",
    "Corp.",
    "Co.",
    "No.",
    "vs.",
)
STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
}
MONTH_NAME_TOKENS = {
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
}

# Known safe quantitative-business metrics. These are intentionally conservative.
KNOWN_METRIC_PHRASES = (
    ("diluted net income per share", "earnings_per_share"),
    ("diluted income per share", "earnings_per_share"),
    ("diluted earnings per share", "earnings_per_share"),
    ("basic net income per share", "earnings_per_share"),
    ("basic income per share", "earnings_per_share"),
    ("basic earnings per share", "earnings_per_share"),
    ("earnings per share", "earnings_per_share"),
    ("net cash provided by operating activities", "operating_cash_flow"),
    ("cash provided by operating activities", "operating_cash_flow"),
    ("cash flow from operating activities", "operating_cash_flow"),
    ("cash flow from operations", "operating_cash_flow"),
    ("operating cash flow", "operating_cash_flow"),
    ("free cash flow", "free_cash_flow"),
    ("nonfarm payroll employment", "payroll_employment"),
    ("nonfarm payrolls", "payroll_employment"),
    ("payroll employment", "payroll_employment"),
    ("payroll jobs", "payroll_employment"),
    ("income from operations", "operating_income"),
    ("profit from operations", "operating_income"),
    ("operating income", "operating_income"),
    ("operating profit", "operating_income"),
    ("operating profit margin", "operating_margin"),
    ("operating margin", "operating_margin"),
    ("gross profit margin", "gross_margin"),
    ("gross margin", "gross_margin"),
    ("gross profit", "gross_profit"),
    ("net income", "net_income"),
    ("net sales", "net_sales"),
    ("net revenues", "revenue"),
    ("net revenue", "revenue"),
    ("revenues", "revenue"),
    ("market share", "market_share"),
    ("market size", "market_size"),
    ("compound annual growth rate", "cagr"),
    ("customer base", "customer_base"),
    ("units sold", "units_sold"),
    ("same-store sales", "same_store_sales"),
    ("gross merchandise value", "gmv"),
    ("book-to-bill ratio", "book_to_bill_ratio"),
    ("operating expenses", "operating_expenses"),
    ("headcount", "headcount"),
    ("revenue", "revenue"),
    ("employment", "employment"),
    ("jobs", "jobs"),
    ("customers", "customers"),
    ("subscribers", "subscribers"),
    ("users", "users"),
    ("sales", "sales"),
    ("ebitda", "ebitda"),
    ("ebit", "ebit"),
    ("gmv", "gmv"),
    ("arr", "arr"),
    ("acv", "acv"),
    ("arpu", "arpu"),
    ("roi", "roi"),
)

METRIC_FALLBACK_CUES = {
    "acv",
    "arr",
    "arpu",
    "backlog",
    "base",
    "billings",
    "bookings",
    "cash",
    "churn",
    "conversion",
    "cost",
    "costs",
    "cagr",
    "customer",
    "customers",
    "demand",
    "ebit",
    "ebitda",
    "earnings",
    "employment",
    "expense",
    "expenses",
    "flow",
    "gmv",
    "growth",
    "income",
    "jobs",
    "margin",
    "market",
    "price",
    "profit",
    "ratio",
    "rate",
    "retention",
    "return",
    "returns",
    "revenue",
    "roi",
    "sales",
    "share",
    "size",
    "spend",
    "subscriber",
    "subscribers",
    "transactions",
    "units",
    "users",
    "utilization",
    "value",
    "visits",
    "volume",
    "yield",
}

DIRECTION_PATTERNS = (
    (
        re.compile(
            r"\b(increas(?:e|ed|es|ing)|grew|growth|rose|risen?|added|gained?|up|improved?)\b",
            re.IGNORECASE,
        ),
        "increase",
    ),
    (
        re.compile(
            r"\b(decreas(?:e|ed|es|ing)|declin(?:e|ed|es|ing)|fell|fallen|lost|down|reduced?|dropped?)\b",
            re.IGNORECASE,
        ),
        "decrease",
    ),
    (
        re.compile(
            r"\b(unchanged|stable|flat|changed little|little change)\b",
            re.IGNORECASE,
        ),
        "stable",
    ),
)

QUALIFIER_PATTERNS = (
    (re.compile(r"\bconstant[- ]currency\b", re.IGNORECASE), "constant_currency"),
    (re.compile(r"\borganic\b", re.IGNORECASE), "organic"),
    (re.compile(r"\badjusted\b", re.IGNORECASE), "adjusted"),
    (re.compile(r"\bnon[- ]gaap\b", re.IGNORECASE), "non_gaap"),
    (re.compile(r"\bgaap\b", re.IGNORECASE), "gaap"),
    (re.compile(r"\bseasonally[- ]adjusted\b", re.IGNORECASE), "seasonally_adjusted"),
    (re.compile(r"\bpreliminary\b", re.IGNORECASE), "preliminary"),
    (re.compile(r"\bestimat(?:e|ed|es)\b", re.IGNORECASE), "estimated"),
    (re.compile(r"\bforecast(?:s|ed|ing)?\b", re.IGNORECASE), "forecast"),
    (re.compile(r"\bproject(?:ed|ion|ions)\b", re.IGNORECASE), "projected"),
    (re.compile(r"\brevised?\b", re.IGNORECASE), "revised"),
)

TOTAL_SCOPE_RE = re.compile(
    r"\b(total|overall|consolidated|company[- ]wide|group[- ]wide|enterprise[- ]wide)\b",
    re.IGNORECASE,
)
NARROWED_SCOPE_RE = re.compile(
    r"\b(segment|segments|division|divisions|business unit|business units|"
    r"product line|product lines|geographic(?:al)?|regional|portfolio|market|markets|"
    r"country|countries|customer group|customer groups)\b",
    re.IGNORECASE,
)
SCOPE_PATTERNS = (
    (
        re.compile(
            r"\b(across all|all|every|broad[- ]based|nationwide|throughout)\b",
            re.IGNORECASE,
        ),
        "universal",
    ),
    (
        re.compile(r"\b(industry|industries|sector|sectors)\b", re.IGNORECASE),
        "industry",
    ),
    (
        re.compile(
            r"\b(province|provinces|state|states|region|regions|geograph(?:y|ic|ical)|countries|markets)\b",
            re.IGNORECASE,
        ),
        "geography",
    ),
    (
        re.compile(
            r"\b(segment|segments|customer group|customer groups)\b", re.IGNORECASE
        ),
        "segment",
    ),
)

BOILERPLATE_HEADING_RE = re.compile(
    r"\b(technical notes?|methodology|definitions?|footnotes?|explanatory notes?)\b",
    re.IGNORECASE,
)
BOILERPLATE_TEXT_PATTERNS = (
    re.compile(r"\btechnical notes?\b", re.IGNORECASE),
    re.compile(r"\bmethodolog(?:y|ical)\b", re.IGNORECASE),
    re.compile(r"\bdefinitions?\b", re.IGNORECASE),
    re.compile(r"\bfootnotes?\b", re.IGNORECASE),
    re.compile(r"\bsampling (?:error|methods?|procedures?)\b", re.IGNORECASE),
    re.compile(r"\bseasonal[- ]adjustment (?:methods?|procedures?)\b", re.IGNORECASE),
    re.compile(r"\bbenchmark revisions?\b", re.IGNORECASE),
    re.compile(r"\bestimates? (?:are|is) subject to revision\b", re.IGNORECASE),
)
MAGNITUDE_MULTIPLIERS = {
    "k": Decimal("1000"),
    "thousand": Decimal("1000"),
    "m": Decimal("1000000"),
    "million": Decimal("1000000"),
    "bn": Decimal("1000000000"),
    "billion": Decimal("1000000000"),
    "trillion": Decimal("1000000000000"),
}
ANCHOR_WEIGHTS = {
    "number": 9.0,
    "number_unit": 11.0,
    "currency": 4.0,
    "date": 8.0,
    "metric": 10.0,
    "metric_phrase": 8.0,
    "entity": 6.0,
    "direction": 5.0,
    "scope": 6.0,
    "qualifier": 6.0,
    "qualifier_context": 3.0,
    "direction_conflict": 4.0,
    "number_conflict": 4.0,
    "keyword": 0.3,
}
ENTITY_EXCLUSIONS = {
    "all",
    "business",
    "fiscal",
    "full",
    "march",
    "april",
    "may",
    "june",
    "july",
    "results",
    "quarterly",
}
IDENTITY_EXCLUSIONS = {
    "basis",
    "calendar",
    "change",
    "changes",
    "consumer",
    "cpi",
    "fiscal",
    "headline",
    "index",
    "month",
    "months",
    "period",
    "periods",
    "point",
    "points",
    "price",
    "prices",
    "quarter",
    "quarters",
    "store",
    "stores",
    "total",
    "year",
    "years",
} | MONTH_NAME_TOKENS | METRIC_FALLBACK_CUES


@dataclass(frozen=True)
class RetrievalQuery:
    claim_text: str
    local_context: str = ""
    top_k: int = 5
    max_chars_per_passage: int = 420
    max_overlap_overflow_chars: int = 180


@dataclass(frozen=True)
class AnchorSet:
    numbers: frozenset[str]
    number_units: frozenset[str]
    currencies: frozenset[str]
    dates: frozenset[str]
    metrics: frozenset[str]
    metric_phrases: frozenset[str]
    entities: frozenset[str]
    directions: frozenset[str]
    scopes: frozenset[str]
    qualifiers: frozenset[str]
    keywords: frozenset[str]


@dataclass(frozen=True)
class ScoredCandidate:
    passage: EvidencePassage
    score: float
    coverage: frozenset[str]
    anchors: AnchorSet
    index: int


def retrieve_candidate_passages(
    extracted_document: ExtractedSourceDocument,
    query: RetrievalQuery,
) -> list[EvidencePassage]:
    """Return up to five diverse original passages for one cited source and claim."""

    max_results = min(max(query.top_k, 0), 5)
    if not extracted_document.blocks or max_results == 0:
        return []

    candidates = _chunk_blocks(
        extracted_document.blocks,
        max_chars_per_passage=max(query.max_chars_per_passage, 1),
        max_overlap_overflow_chars=max(query.max_overlap_overflow_chars, 0),
    )
    claim_anchors = _anchors(query.claim_text)
    context_anchors = _anchors(query.local_context)
    scored = [
        _score_candidate(
            claim_anchors=claim_anchors,
            context_anchors=context_anchors,
            candidate=candidate,
            candidate_index=index,
        )
        for index, candidate in enumerate(candidates)
    ]
    scored = _apply_identity_and_fragment_adjustments(
        scored,
        claim_identity_terms=_identity_terms(query.claim_text),
    )
    meaningful = [candidate for candidate in scored if candidate.score > 0]
    meaningful.sort(
        key=lambda item: (
            item.score,
            -(item.passage.locator.page_number or 0),
            item.passage.passage_id,
        ),
        reverse=True,
    )
    return _select_diverse_passages(meaningful, max_results=max_results)


def _select_diverse_passages(
    candidates: list[ScoredCandidate],
    *,
    max_results: int,
) -> list[EvidencePassage]:
    selected: list[ScoredCandidate] = []
    covered: set[str] = set()
    remaining = list(candidates)

    while remaining and len(selected) < max_results:
        if not selected:
            chosen = remaining.pop(0)
        else:
            choices: list[tuple[float, ScoredCandidate]] = []
            for candidate in remaining:
                if _is_near_duplicate(
                    candidate.passage,
                    [item.passage for item in selected],
                ):
                    continue

                new_material = {
                    anchor
                    for anchor in candidate.coverage - covered
                    if not anchor.startswith("keyword:")
                }
                novelty = sum(_coverage_weight(anchor) for anchor in new_material)
                context_value = _context_value(new_material)
                corroboration = _corroboration_value(candidate.coverage)

                if not new_material and context_value <= 0 and corroboration <= 0:
                    continue

                utility = candidate.score + novelty * 1.35 + context_value + corroboration
                choices.append((utility, candidate))

            if not choices:
                break

            _, chosen = max(
                choices,
                key=lambda item: (item[0], item[1].passage.passage_id),
            )
            remaining.remove(chosen)

        selected.append(chosen)
        covered.update(chosen.coverage)

    # Diversity comes first, but leaving unused slots can hide a distinct
    # positive-score passage that the downstream judge needs. Backfill in the
    # existing score order while retaining the same near-duplicate guard.
    for candidate in remaining:
        if len(selected) >= max_results:
            break
        if _is_near_duplicate(
            candidate.passage,
            [item.passage for item in selected],
        ):
            continue
        selected.append(candidate)
        covered.update(candidate.coverage)

    return [
        item.passage.model_copy(update={"retrieval_score": round(item.score, 3)})
        for item in selected
    ]


def _context_value(new_material: set[str]) -> float:
    value = 0.0
    if any(anchor.startswith("qualifier_context:") for anchor in new_material):
        value += 4.0
    if any(anchor.startswith("direction_conflict:") for anchor in new_material):
        value += 5.0
    if any(anchor.startswith("number_conflict:") for anchor in new_material):
        value += 5.0
    return value


def _corroboration_value(coverage: frozenset[str]) -> float:
    prefixes = {anchor.split(":", 1)[0] for anchor in coverage}
    if {"number", "metric"}.issubset(prefixes) or {"number", "metric_phrase"}.issubset(prefixes):
        return 2.0
    if {"date", "metric"}.issubset(prefixes) or {"date", "metric_phrase"}.issubset(prefixes):
        return 1.5
    return 0.0


def _chunk_blocks(
    blocks: Iterable[SourceTextBlock],
    *,
    max_chars_per_passage: int,
    max_overlap_overflow_chars: int,
) -> list[EvidencePassage]:
    block_list = list(blocks)
    passages: list[EvidencePassage] = []

    for block in block_list:
        if _is_structured_table_row_block(block):
            # A table row is already a self-contained evidence record: title,
            # header context, and its original row text. Do not split it into
            # sentence fragments, because that could separate the row from its
            # table context.
            passages.append(_build_passage(block, [block.text], chunk_index=1))
            continue

        passages.extend(
            _chunk_single_block(
                block,
                max_chars_per_passage=max_chars_per_passage,
                max_overlap_overflow_chars=max_overlap_overflow_chars,
            )
        )

    for left_block, right_block in pairwise(block_list):
        if not _blocks_share_context(left_block, right_block):
            continue

        window_text = _boundary_window_text(
            left_block.text,
            right_block.text,
            max_chars=max_chars_per_passage + max_overlap_overflow_chars,
        )
        if window_text:
            passages.append(_build_window_passage(left_block, right_block, window_text))

    return passages


def _chunk_single_block(
    block: SourceTextBlock,
    *,
    max_chars_per_passage: int,
    max_overlap_overflow_chars: int,
) -> list[EvidencePassage]:
    """Create sentence-safe chunks with one-sentence overlap across boundaries."""

    passages: list[EvidencePassage] = []
    sentences = _sentence_chunks(block.text)
    current_sentences: list[str] = []
    chunk_index = 1
    soft_limit = max_chars_per_passage
    hard_limit = max_chars_per_passage + max_overlap_overflow_chars

    for sentence in sentences:
        if not current_sentences:
            current_sentences = [sentence]
            continue

        proposed = _join_sentences([*current_sentences, sentence])
        if len(proposed) <= soft_limit:
            current_sentences.append(sentence)
            continue

        passages.append(_build_passage(block, current_sentences, chunk_index))
        chunk_index += 1

        overlap = current_sentences[-1]
        overlapped = _join_sentences([overlap, sentence])
        if len(overlapped) <= hard_limit:
            current_sentences = [overlap, sentence]
        else:
            current_sentences = [sentence]

    if current_sentences:
        passages.append(_build_passage(block, current_sentences, chunk_index))

    return passages


def _boundary_window_text(left_text: str, right_text: str, *, max_chars: int) -> str | None:
    combined = f"{left_text} {right_text}".strip()
    if len(combined) <= max_chars:
        return combined

    left_sentences = _sentence_chunks(left_text)
    right_sentences = _sentence_chunks(right_text)
    if not left_sentences or not right_sentences:
        return None

    left_window = [left_sentences[-1]]
    right_window = [right_sentences[0]]
    if len(_join_sentences([*left_window, *right_window])) > max_chars:
        return None

    left_index = len(left_sentences) - 2
    right_index = 1

    while True:
        added = False

        if left_index >= 0:
            candidate_left = [left_sentences[left_index], *left_window]
            candidate_text = _join_sentences([*candidate_left, *right_window])
            if len(candidate_text) <= max_chars:
                left_window = candidate_left
                left_index -= 1
                added = True

        if right_index < len(right_sentences):
            candidate_right = [*right_window, right_sentences[right_index]]
            candidate_text = _join_sentences([*left_window, *candidate_right])
            if len(candidate_text) <= max_chars:
                right_window = candidate_right
                right_index += 1
                added = True

        if not added:
            break
        if left_index < 0 and right_index >= len(right_sentences):
            break

    return _join_sentences([*left_window, *right_window])


def _join_sentences(sentences: Iterable[str]) -> str:
    return " ".join(sentence.strip() for sentence in sentences if sentence.strip())


def _build_passage(
    block: SourceTextBlock,
    sentences: list[str],
    chunk_index: int,
) -> EvidencePassage:
    text_span_label = block.locator.text_span_label or block.block_id
    locator = block.locator.model_copy(
        update={"text_span_label": f"{text_span_label}-chunk-{chunk_index}"}
    )
    return EvidencePassage(
        passage_id=f"{block.block_id}-chunk-{chunk_index}",
        source_id=block.source_id,
        text=_join_sentences(sentences),
        locator=locator,
        retrieval_score=None,
    )


def _build_window_passage(
    left_block: SourceTextBlock,
    right_block: SourceTextBlock,
    combined_text: str,
) -> EvidencePassage:
    left_label = left_block.locator.text_span_label or left_block.block_id
    right_label = right_block.locator.text_span_label or right_block.block_id
    locator = right_block.locator.model_copy(
        update={
            "heading": right_block.locator.heading or left_block.locator.heading,
            "text_span_label": f"{left_label}+{right_label}-boundary-window",
        }
    )
    return EvidencePassage(
        passage_id=f"{left_block.block_id}+{right_block.block_id}-boundary-window",
        source_id=right_block.source_id,
        text=combined_text,
        locator=locator,
        retrieval_score=None,
    )


def _blocks_share_context(left: SourceTextBlock, right: SourceTextBlock) -> bool:
    # Boundary windows are for adjacent prose whose meaning may span a block
    # boundary. Structured table rows already carry their own table title and
    # header context, so combining them with prose or another row creates
    # misleading hybrid evidence.
    if _is_structured_table_row_block(left) or _is_structured_table_row_block(right):
        return False
    if left.source_id != right.source_id:
        return False
    if left.locator.page_number != right.locator.page_number:
        return False
    left_heading = (left.locator.heading or "").strip().lower()
    right_heading = (right.locator.heading or "").strip().lower()
    return not left_heading or not right_heading or left_heading == right_heading


def _is_structured_table_row_block(block: SourceTextBlock) -> bool:
    """Return true for adapter-produced table rows, not ordinary prose.

    This intentionally checks the normalized evidence shape, rather than a
    publisher, page number, or source-specific table name. Source adapters emit
    these labels only after detecting a table-like row, so the retriever can
    preserve that record as an atomic passage.
    """

    label = block.locator.text_span_label or ""
    if re.search(r"(?:^|-)table-\d+-row-\d+(?:$|-)", label):
        return True

    text = block.text.lstrip()
    return (text.startswith("Table: ") and " Row: " in text) or text.startswith("Row: ")


def _score_candidate(
    *,
    claim_anchors: AnchorSet,
    context_anchors: AnchorSet,
    candidate: EvidencePassage,
    candidate_index: int,
) -> ScoredCandidate:
    heading = candidate.locator.heading or ""
    combined_text = f"{heading} {candidate.text}".strip()
    candidate_anchors = _anchors(combined_text)
    coverage = _matching_coverage(claim_anchors, candidate_anchors)

    central_overlap = _has_central_overlap(coverage)
    if not central_overlap:
        return ScoredCandidate(
            passage=candidate,
            score=0.0,
            coverage=frozenset(),
            anchors=candidate_anchors,
            index=candidate_index,
        )

    if _has_direction_conflict(
        claim_anchors,
        candidate_anchors,
        central_overlap=central_overlap,
    ):
        coverage.add("direction_conflict:" + ",".join(sorted(candidate_anchors.directions)))

    if _has_number_conflict(
        claim_anchors,
        candidate_anchors,
        coverage=coverage,
    ):
        coverage.add("number_conflict:present")

    if central_overlap:
        for qualifier in candidate_anchors.qualifiers - claim_anchors.qualifiers:
            coverage.add(f"qualifier_context:{qualifier}")

    score = sum(_coverage_weight(anchor) for anchor in coverage)
    score += 0.35 * len(context_anchors.keywords & candidate_anchors.keywords)
    score += 1.35 * len(context_anchors.entities & candidate_anchors.entities)

    material_categories = {
        anchor.split(":", 1)[0]
        for anchor in coverage
        if not anchor.startswith("keyword:")
    }
    score += min(len(material_categories) ** 2 * 0.45, 7.0)
    score += _heading_priority_boost(heading)

    score -= _metric_mismatch_penalty(claim_anchors, candidate_anchors, coverage=coverage)
    score -= _period_mismatch_penalty(claim_anchors, candidate_anchors)
    score -= _currency_mismatch_penalty(claim_anchors, candidate_anchors)
    score -= _scope_mismatch_penalty(claim_anchors, candidate_anchors)

    boilerplate_penalty = _boilerplate_penalty(heading=heading, text=candidate.text)
    if central_overlap:
        boilerplate_penalty *= 0.35
    score -= boilerplate_penalty

    return ScoredCandidate(
        passage=candidate,
        score=score,
        coverage=frozenset(coverage),
        anchors=candidate_anchors,
        index=candidate_index,
    )


def _apply_identity_and_fragment_adjustments(
    candidates: list[ScoredCandidate],
    *,
    claim_identity_terms: set[str],
) -> list[ScoredCandidate]:
    adjusted: list[ScoredCandidate] = []

    for candidate in candidates:
        score = candidate.score
        score += _identity_bonus(
            claim_identity_terms=claim_identity_terms,
            candidate_text=candidate.passage.text,
        )
        score -= _fragment_penalty(
            candidate=candidate,
            candidates=candidates,
            claim_identity_terms=claim_identity_terms,
        )
        adjusted.append(
            ScoredCandidate(
                passage=candidate.passage,
                score=score,
                coverage=candidate.coverage,
                anchors=candidate.anchors,
                index=candidate.index,
            )
        )

    return adjusted


def _identity_bonus(*, claim_identity_terms: set[str], candidate_text: str) -> float:
    if not claim_identity_terms:
        return 0.0

    overlap = claim_identity_terms & _identity_terms(candidate_text)
    if len(overlap) >= 2:
        return min(2.5 * len(overlap), 6.0)
    if len(overlap) == 1 and len(claim_identity_terms) == 1:
        return 1.5
    return 0.0


def _fragment_penalty(
    *,
    candidate: ScoredCandidate,
    candidates: list[ScoredCandidate],
    claim_identity_terms: set[str],
) -> float:
    if not _is_fragment_like_candidate(candidate):
        return 0.0

    candidate_identity_overlap = len(
        claim_identity_terms & _identity_terms(candidate.passage.text)
    )
    material_coverage = {
        anchor.split(":", 1)[0]
        for anchor in candidate.coverage
        if not anchor.startswith("keyword:")
    }
    best_penalty = 0.0

    for other in candidates:
        if other is candidate or other.passage.source_id != candidate.passage.source_id:
            continue
        if other.passage.locator.page_number != candidate.passage.locator.page_number:
            continue
        if (
            candidate.passage.locator.heading or ""
        ).strip().lower() != (other.passage.locator.heading or "").strip().lower():
            continue
        if abs(other.index - candidate.index) > 16:
            continue
        if _is_fragment_like_candidate(other):
            continue
        if not _shares_fragment_story(candidate.anchors, other.anchors):
            continue

        other_identity_overlap = len(
            claim_identity_terms & _identity_terms(other.passage.text)
        )
        other_material_coverage = {
            anchor.split(":", 1)[0]
            for anchor in other.coverage
            if not anchor.startswith("keyword:")
        }
        richer_text = len(other.passage.text) >= len(candidate.passage.text) + 20
        richer_identity = other_identity_overlap > candidate_identity_overlap
        richer_material = len(other_material_coverage) > len(material_coverage)

        if not richer_text or not (richer_identity or richer_material):
            continue

        penalty = 6.0
        if richer_identity:
            penalty += min(
                (other_identity_overlap - candidate_identity_overlap) * 0.75,
                2.0,
            )
        if richer_material:
            penalty += 0.75
        best_penalty = max(best_penalty, penalty)

    return best_penalty


def _is_fragment_like_candidate(candidate: ScoredCandidate) -> bool:
    if candidate.score <= 0:
        return False
    if len(candidate.passage.text.strip()) > 64:
        return False

    material_coverage = {
        anchor.split(":", 1)[0]
        for anchor in candidate.coverage
        if not anchor.startswith("keyword:")
    }
    if not material_coverage <= {"number", "number_unit", "date"}:
        return False
    if not {"number", "number_unit"} & material_coverage:
        return False

    if _identity_terms(candidate.passage.text):
        return False
    return len(_tokens(candidate.passage.text)) <= 6


def _shares_fragment_story(candidate: AnchorSet, other: AnchorSet) -> bool:
    shared_number = bool(candidate.numbers & other.numbers)
    shared_number_unit = bool(candidate.number_units & other.number_units)
    shared_date = bool(_matching_dates(candidate.dates, other.dates))
    return shared_number and (shared_number_unit or shared_date)


def _matching_coverage(query: AnchorSet, candidate: AnchorSet) -> set[str]:
    coverage: set[str] = set()
    metric_matches = query.metrics & candidate.metrics
    value_pairs = (
        ("number", query.numbers, candidate.numbers),
        ("number_unit", query.number_units, candidate.number_units),
        ("currency", query.currencies, candidate.currencies),
        ("metric", query.metrics, candidate.metrics),
        ("entity", query.entities, candidate.entities),
        ("direction", query.directions, candidate.directions),
        ("scope", query.scopes, candidate.scopes),
        ("qualifier", query.qualifiers, candidate.qualifiers),
        ("keyword", query.keywords, candidate.keywords),
    )
    for prefix, query_values, candidate_values in value_pairs:
        coverage.update(f"{prefix}:{value}" for value in query_values & candidate_values)

    if not metric_matches:
        coverage.update(
            f"metric_phrase:{value}"
            for value in query.metric_phrases & candidate.metric_phrases
        )

    coverage.update(f"date:{value}" for value in _matching_dates(query.dates, candidate.dates))
    return coverage


def _matching_dates(query_dates: frozenset[str], candidate_dates: frozenset[str]) -> set[str]:
    """Prefer exact period matches, then allow only safe finance-style relations."""

    query_quarters = {value for value in query_dates if value.startswith("quarter:")}
    candidate_quarters = {value for value in candidate_dates if value.startswith("quarter:")}
    query_months = {value for value in query_dates if value.startswith("month:")}
    candidate_months = {value for value in candidate_dates if value.startswith("month:")}
    query_fiscal_years = {value for value in query_dates if value.startswith("fiscal_year:")}
    candidate_fiscal_years = {value for value in candidate_dates if value.startswith("fiscal_year:")}
    query_years = {value for value in query_dates if value.startswith("year:")}
    candidate_years = {value for value in candidate_dates if value.startswith("year:")}

    if query_quarters:
        exact = query_quarters & candidate_quarters
        if exact:
            return exact

        related_months: set[str] = set()
        for query_quarter in query_quarters:
            parsed_query = _parse_quarter_tag(query_quarter)
            if parsed_query is None:
                continue
            period_kind, quarter, year = parsed_query
            if period_kind != "calendar":
                continue
            for candidate_month in candidate_months:
                parsed_month = _parse_month_tag(candidate_month)
                if parsed_month is None:
                    continue
                candidate_year, candidate_month_name = parsed_month
                if candidate_year == year and _month_to_calendar_quarter(candidate_month_name) == quarter:
                    related_months.add(candidate_month)
        if related_months:
            return related_months

    if query_months:
        exact = query_months & candidate_months
        if exact:
            return exact

        related_quarters: set[str] = set()
        for query_month in query_months:
            parsed_month = _parse_month_tag(query_month)
            if parsed_month is None:
                continue
            year, month_name = parsed_month
            query_quarter = _month_to_calendar_quarter(month_name)
            for candidate_quarter in candidate_quarters:
                parsed_quarter = _parse_quarter_tag(candidate_quarter)
                if parsed_quarter is None:
                    continue
                period_kind, quarter, candidate_year = parsed_quarter
                if period_kind == "calendar" and quarter == query_quarter and candidate_year == year:
                    related_quarters.add(candidate_quarter)
        if related_quarters:
            return related_quarters

    if query_fiscal_years:
        exact = query_fiscal_years & candidate_fiscal_years
        if exact:
            return exact

        related_fiscal_quarters: set[str] = set()
        for query_fiscal_year in query_fiscal_years:
            fiscal_year = query_fiscal_year.split(":", 1)[1]
            for candidate_quarter in candidate_quarters:
                parsed_quarter = _parse_quarter_tag(candidate_quarter)
                if parsed_quarter is None:
                    continue
                period_kind, _, candidate_year = parsed_quarter
                if period_kind == "fiscal" and candidate_year == fiscal_year:
                    related_fiscal_quarters.add(candidate_quarter)
        if related_fiscal_quarters:
            return related_fiscal_quarters

    if query_years:
        return query_years & candidate_years

    return set()


def _parse_quarter_tag(value: str) -> tuple[str, str, str] | None:
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != "quarter":
        return None
    _, period_kind, quarter, year = parts
    if period_kind not in {"calendar", "fiscal"}:
        return None
    return period_kind, quarter, year


def _parse_month_tag(value: str) -> tuple[str, str] | None:
    parts = value.split(":", 1)
    if len(parts) != 2 or parts[0] != "month":
        return None
    year, month_name = parts[1].split("-", 1)
    return year, month_name


def _month_to_calendar_quarter(month_name: str) -> str:
    month_number = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }[month_name]
    return str(((month_number - 1) // 3) + 1)


def _coverage_weight(anchor: str) -> float:
    return ANCHOR_WEIGHTS[anchor.split(":", 1)[0]]


def _has_central_overlap(coverage: set[str]) -> bool:
    return any(
        anchor.startswith(("number:", "number_unit:", "date:", "metric:", "metric_phrase:", "entity:"))
        for anchor in coverage
    )


def _has_direction_conflict(
    claim_anchors: AnchorSet,
    candidate_anchors: AnchorSet,
    *,
    central_overlap: bool,
) -> bool:
    return bool(
        central_overlap
        and claim_anchors.directions
        and candidate_anchors.directions
        and claim_anchors.directions.isdisjoint(candidate_anchors.directions)
    )


def _has_number_conflict(
    claim_anchors: AnchorSet,
    candidate_anchors: AnchorSet,
    *,
    coverage: set[str],
) -> bool:
    if not claim_anchors.numbers or not candidate_anchors.numbers:
        return False
    if claim_anchors.numbers & candidate_anchors.numbers:
        return False

    shared_identity = bool(
        claim_anchors.metrics & candidate_anchors.metrics
        or claim_anchors.metric_phrases & candidate_anchors.metric_phrases
        or claim_anchors.entities & candidate_anchors.entities
        or _matching_dates(claim_anchors.dates, candidate_anchors.dates)
    )
    has_metric_or_date = any(
        anchor.startswith(("metric:", "metric_phrase:", "date:")) for anchor in coverage
    )
    shared_unit_kind = bool(
        _unit_kinds(claim_anchors.number_units) & _unit_kinds(candidate_anchors.number_units)
    )
    return shared_identity and has_metric_or_date and shared_unit_kind


def _unit_kinds(number_units: frozenset[str]) -> set[str]:
    kinds: set[str] = set()
    for value in number_units:
        parts = value.split(":")
        if len(parts) >= 2:
            kinds.add(parts[1])
    return kinds


def _metric_mismatch_penalty(
    query: AnchorSet,
    candidate: AnchorSet,
    *,
    coverage: set[str],
) -> float:
    if any(
        anchor.startswith(("metric:", "metric_phrase:"))
        for anchor in coverage
    ):
        return 0.0

    if query.metrics and candidate.metrics and query.metrics.isdisjoint(candidate.metrics):
        return 10.0

    # Fallback phrases are discovery hints, not canonical metric identities.
    # Their absence of exact overlap can result from ordinary wording changes
    # (word order, inflection, or short connecting words), so it must stay
    # neutral rather than becoming negative evidence.
    return 0.0


def _period_mismatch_penalty(query: AnchorSet, candidate: AnchorSet) -> float:
    if not query.dates or not candidate.dates:
        return 0.0
    if _matching_dates(query.dates, candidate.dates):
        return 0.0

    if any(value.startswith("quarter:") for value in query.dates):
        return 10.0
    if any(value.startswith("month:") for value in query.dates):
        return 9.0
    if any(value.startswith("fiscal_year:") for value in query.dates):
        return 8.0
    if any(value.startswith("year:") for value in query.dates):
        return 6.0
    return 0.0


def _currency_mismatch_penalty(query: AnchorSet, candidate: AnchorSet) -> float:
    if query.currencies and candidate.currencies and query.currencies.isdisjoint(candidate.currencies):
        return 10.0
    return 0.0


def _scope_mismatch_penalty(query: AnchorSet, candidate: AnchorSet) -> float:
    if "total_company" in query.scopes and "narrowed" in candidate.scopes:
        return 10.0
    if "universal" in query.scopes and {"segment", "geography", "narrowed"} & candidate.scopes:
        return 8.0
    return 0.0


def _anchors(text: str) -> AnchorSet:
    numbers, number_units, currencies = _number_anchors(text)
    metrics = _metrics(text)
    return AnchorSet(
        numbers=frozenset(numbers),
        number_units=frozenset(number_units),
        currencies=frozenset(currencies),
        dates=frozenset(_dates(text)),
        metrics=frozenset(metrics),
        metric_phrases=frozenset(_metric_phrase_fallbacks(text)),
        entities=frozenset(_entities(text)),
        directions=frozenset(_directions(text)),
        scopes=frozenset(_scopes(text)),
        qualifiers=frozenset(_qualifiers(text)),
        keywords=frozenset(_tokens(text)),
    )


def _tokens(text: str) -> set[str]:
    return {
        token
        for match in TOKEN_RE.finditer(text)
        if (token := match.group(0).lower()) not in STOPWORDS
    }


def _number_anchors(text: str) -> tuple[set[str], set[str], set[str]]:
    numbers: set[str] = set()
    number_units: set[str] = set()
    currencies: set[str] = set()
    period_year_spans = _period_year_spans(text)

    for match in NUMBER_WITH_UNIT_RE.finditer(text):
        raw_number = match.group("number").replace(",", "")
        try:
            value = Decimal(raw_number)
        except InvalidOperation:
            continue

        magnitude = (match.group("magnitude") or "").lower()
        value *= MAGNITUDE_MULTIPLIERS.get(magnitude, Decimal("1"))
        number = _decimal_key(value)
        currency_signal = bool(
            match.group("currency_prefix")
            or match.group("currency_suffix")
            or (match.group("unit") or "").lower().startswith("dollar")
        )
        unit = _canonical_unit(match.group("unit"))

        # A year gets date credit through _dates(). Suppress generic numeric
        # credit only when this exact numeric occurrence sits inside a
        # recognized period expression, such as "May 2026" or "in 2026".
        # A separate occurrence, for example "2026 stores", remains numeric.
        if _is_period_year_occurrence(match.span("number"), period_year_spans):
            continue

        numbers.add(number)
        currency = _canonical_currency(
            prefix=match.group("currency_prefix"),
            suffix=match.group("currency_suffix"),
        )
        if currency_signal:
            number_units.add(f"{number}:currency")
            if currency:
                number_units.add(f"{number}:currency:{currency}")
                currencies.add(currency)
            continue

        if unit:
            number_units.add(f"{number}:{unit}")

    return numbers, number_units, currencies


def _period_year_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return character spans for years used as explicit period expressions.

    This is deliberately occurrence-based. It does not classify every 1900-2099
    number as a date, because the same digits can appear elsewhere as a quantity.
    """

    spans: set[tuple[int, int]] = set()

    for match in MONTH_PERIOD_RE.finditer(text):
        spans.add(match.span("year"))

    for match in QUARTER_RE.finditer(text):
        if match.group("year"):
            spans.add(match.span("year"))

    for match in FISCAL_YEAR_RE.finditer(text):
        spans.add(match.span(1))

    # Temporal prepositions and common date phrases, including "in 2026".
    for match in re.finditer(
        r"\b(?:in|during|for|by|since|until|through|throughout|before|after|"
        r"from)\s+(?:the\s+)?(?P<year>(?:19|20)\d{2})\b",
        text,
        re.IGNORECASE,
    ):
        spans.add(match.span("year"))

    # A range makes both endpoints temporal even when only the first has a
    # preposition, e.g. "from 2025 to 2026".
    for match in re.finditer(
        r"\b(?P<start>(?:19|20)\d{2})\s*(?:to|through|[-–])\s*"
        r"(?P<end>(?:19|20)\d{2})\b",
        text,
        re.IGNORECASE,
    ):
        spans.add(match.span("start"))
        spans.add(match.span("end"))

    return tuple(sorted(spans))


def _is_period_year_occurrence(
    number_span: tuple[int, int],
    period_year_spans: tuple[tuple[int, int], ...],
) -> bool:
    return number_span in period_year_spans


def _decimal_key(value: Decimal) -> str:
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _canonical_currency(*, prefix: str | None, suffix: str | None) -> str | None:
    raw = " ".join(part for part in (prefix, suffix) if part).strip().lower()
    if not raw:
        return None

    compact = raw.replace(" ", "")
    if compact in {"usd", "us$"}:
        return "usd"
    if compact in {"cad", "c$"}:
        return "cad"
    if compact in {"eur", "\u20ac"}:
        return "eur"
    if compact in {"gbp", "\u00a3"}:
        return "gbp"
    if compact in {"cny", "rmb", "cn$", "cn\u00a5", "rmb\u00a5"}:
        return "cny"
    if compact == "jpy":
        return "jpy"
    if compact in {"inr", "\u20b9"}:
        return "inr"
    if compact in {"idr", "rp", "rp."}:
        return "idr"
    if compact in {"aud", "a$"}:
        return "aud"
    if compact in {"hkd", "hk$"}:
        return "hkd"
    if compact in {"sgd", "s$"}:
        return "sgd"
    return None


def _canonical_unit(unit: str | None) -> str | None:
    if not unit:
        return None

    lowered = " ".join(unit.lower().split())
    if lowered == "%" or lowered.startswith("percent"):
        return "percentage_point" if "point" in lowered else "percent"
    if lowered in {"basis point", "basis points", "bp", "bps"}:
        return "basis_point"
    if lowered in {"job", "jobs"}:
        return "job"
    if lowered in {"employee", "employees"}:
        return "employee"
    if lowered in {"worker", "workers"}:
        return "worker"
    if lowered in {"person", "people"}:
        return "people"
    if lowered in {"customer", "customers"}:
        return "customer"
    if lowered in {"subscriber", "subscribers"}:
        return "subscriber"
    if lowered in {"user", "users"}:
        return "user"
    if lowered in {"unit", "units"}:
        return "unit"
    if lowered in {"share", "shares"}:
        return "share"
    if lowered in {"transaction", "transactions"}:
        return "transaction"
    if lowered in {"visit", "visits"}:
        return "visit"
    return lowered.rstrip("s")


def _metrics(text: str) -> set[str]:
    lowered = text.lower()
    return {canonical for phrase, canonical in KNOWN_METRIC_PHRASES if phrase in lowered}


def _metric_phrase_fallbacks(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9&'/-]*", text.lower())
    phrases: set[str] = set()
    known_phrases = {phrase for phrase, _ in KNOWN_METRIC_PHRASES}

    for width in (1, 2, 3, 4, 5):
        for start in range(0, max(0, len(words) - width + 1)):
            phrase_words = words[start : start + width]
            if phrase_words[0] in STOPWORDS or phrase_words[-1] in STOPWORDS:
                continue

            normalized_phrase = " ".join(phrase_words)
            if normalized_phrase in known_phrases:
                continue

            content_words = [word for word in phrase_words if word not in STOPWORDS]
            if not content_words:
                continue

            contains_metric_cue = any(
                word in METRIC_FALLBACK_CUES or word.rstrip("s") in METRIC_FALLBACK_CUES
                for word in content_words
            )
            if not contains_metric_cue:
                continue

            if width == 1 and content_words[0] not in {"arr", "acv", "arpu", "gmv", "roi"}:
                continue

            phrases.add(normalized_phrase)

    ranked = sorted(
        phrases,
        key=lambda phrase: (len(phrase.split()), len(phrase), phrase),
        reverse=True,
    )
    return set(ranked[:24])


def _dates(text: str) -> set[str]:
    dates: set[str] = set()

    for match in MONTH_PERIOD_RE.finditer(text):
        month = _canonical_month(match.group("month"))
        dates.add(f"month:{match.group('year')}-{month}")

    dates.update(f"year:{match.group(0)}" for match in YEAR_RE.finditer(text))

    quarter_words = {"first": "1", "second": "2", "third": "3", "fourth": "4"}
    for match in QUARTER_RE.finditer(text):
        quarter = match.group("number") or quarter_words[match.group("word").lower()]
        year = match.group("year")
        fiscal = bool(match.group("fiscal"))
        period_kind = "fiscal" if fiscal else "calendar"
        if year:
            dates.add(f"quarter:{period_kind}:{quarter}:{year}")
        else:
            dates.add(f"quarter:unspecified:{quarter}")

    dates.update(f"fiscal_year:{match.group(1)}" for match in FISCAL_YEAR_RE.finditer(text))
    return dates


def _canonical_month(raw_month: str) -> str:
    normalized = raw_month.lower().rstrip(".")
    return {
        "jan": "january",
        "feb": "february",
        "mar": "march",
        "apr": "april",
        "jun": "june",
        "jul": "july",
        "aug": "august",
        "sep": "september",
        "sept": "september",
        "oct": "october",
        "nov": "november",
        "dec": "december",
    }.get(normalized, normalized)


def _entities(text: str) -> set[str]:
    entities: set[str] = set()
    for match in ENTITY_RE.finditer(text):
        entity = " ".join(match.group(0).lower().split())
        if entity not in ENTITY_EXCLUSIONS and len(entity) > 1:
            entities.add(entity)
    return entities


def _directions(text: str) -> set[str]:
    return {canonical for pattern, canonical in DIRECTION_PATTERNS if pattern.search(text)}


def _scopes(text: str) -> set[str]:
    scopes = {canonical for pattern, canonical in SCOPE_PATTERNS if pattern.search(text)}
    if TOTAL_SCOPE_RE.search(text):
        scopes.add("total_company")
    if NARROWED_SCOPE_RE.search(text):
        scopes.add("narrowed")
    return scopes


def _qualifiers(text: str) -> set[str]:
    return {canonical for pattern, canonical in QUALIFIER_PATTERNS if pattern.search(text)}


def _identity_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in _tokens(text):
        if any(character.isdigit() for character in token):
            continue
        normalized = _normalize_identity_token(token)
        if len(normalized) < 4:
            continue
        if normalized in IDENTITY_EXCLUSIONS:
            continue
        terms.add(normalized)
    return terms


def _normalize_identity_token(token: str) -> str:
    normalized = token.lower().strip("-'/")
    if normalized.endswith("ies") and len(normalized) > 4:
        return normalized[:-3] + "y"
    if normalized.endswith(("ches", "shes", "xes", "zes", "ses")) and len(normalized) > 4:
        return normalized[:-2]
    if normalized.endswith("s") and not normalized.endswith("ss") and len(normalized) > 4:
        return normalized[:-1]
    return normalized


def _heading_priority_boost(heading: str) -> float:
    normalized = " ".join(heading.lower().split())
    if not normalized:
        return 0.0
    if re.search(r"\b(abstract|executive summary|summary|key findings?|findings?|highlights?)\b", normalized):
        return 6.0
    if re.search(r"\b(overview|introduction|results?)\b", normalized):
        return 2.0
    return 0.0


def _boilerplate_penalty(*, heading: str, text: str) -> float:
    heading_penalty = 36.0 if BOILERPLATE_HEADING_RE.search(heading) else 0.0
    text_matches = sum(bool(pattern.search(text)) for pattern in BOILERPLATE_TEXT_PATTERNS)
    return heading_penalty + min(text_matches * 10.0, 30.0)


def _is_near_duplicate(
    candidate: EvidencePassage,
    selected: list[EvidencePassage],
) -> bool:
    candidate_tokens = _tokens(candidate.text)
    if not candidate_tokens:
        return False

    for existing in selected:
        existing_tokens = _tokens(existing.text)
        union = candidate_tokens | existing_tokens
        if union and len(candidate_tokens & existing_tokens) / len(union) >= 0.82:
            return True
    return False


def _sentence_chunks(text: str) -> list[str]:
    if not text.strip():
        return []

    protected = re.sub(r"(?<=\d)\.(?=\d)", PERIOD_SENTINEL, text)
    for abbreviation in COMMON_ABBREVIATIONS:
        protected = re.sub(
            re.escape(abbreviation),
            abbreviation.replace(".", PERIOD_SENTINEL),
            protected,
            flags=re.IGNORECASE,
        )
    protected = INITIALISM_RE.sub(
        lambda match: match.group(0).replace(".", PERIOD_SENTINEL),
        protected,
    )
    sentences = [
        chunk.replace(PERIOD_SENTINEL, ".").strip()
        for chunk in SENTENCE_BOUNDARY_RE.split(protected)
        if chunk.strip()
    ]
    return sentences or [text.strip()]
