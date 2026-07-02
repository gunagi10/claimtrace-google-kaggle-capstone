"""Application service layer for the local ClaimTrace review workflow.

FastAPI routes call into this module for the real work: DOCX parsing, source
resolution, deterministic retrieval, Gemini judgment, batch source reuse, section
analysis, and final coherence. Keeping that orchestration here makes the browser
page thin and leaves the review pipeline testable without UI automation.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import settings
from app.docx_intake import DocxIntakeError, parse_docx_bytes
from app.evidence_judge import JudgeConfigurationError, judge_evidence_payload
from app.final_coherence import build_final_coherence_packet, run_final_coherence
from app.final_coherence_judge import FinalCoherenceConfigurationError
from app.review_models import (
    AtomicClaim,
    BatchCoverage,
    BatchGateRecommendation,
    CitationDirection,
    ClaimReadySentence,
    EvidenceVerdict,
    EvidencePassage,
    ExtractedSourceDocument,
    FinalCoherenceAssessment,
    FinalCoherencePacket,
    ParsedDocument,
    ReferenceEntry,
    ReviewTrace,
    SectionClaimOutcome,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
)
from app.review_orchestrator import (
    DeterministicReviewFromDocumentRequest,
    run_deterministic_evidence_review_from_document,
)
from app.section_analysis import (
    SectionAnalysisRunItem,
    SectionConcurrencyDebug,
    build_section_packets,
    run_section_packets_with_bounded_concurrency,
)
from app.source_adapters import SourcePayload, extract_source_document
from app.source_fetcher import (
    fetch_exact_source,
    fetch_rendered_exact_source,
    should_try_browser_fallback,
)


CITATION_MARKER_RE = re.compile(r"\[\d+\]")
MAX_CONCURRENT_SOURCE_WORKERS = 5


class PrepareReviewResponse(BaseModel):
    sections: list[dict]
    references: list[ReferenceEntry]
    claim_ready_sentences: list[dict]
    warnings: list[str] = Field(default_factory=list)


class RunReviewResponse(BaseModel):
    status: str
    judge_payload: dict | None = None
    assessment: dict | None = None
    message: str | None = None
    trace: ReviewTrace | None = None


@dataclass(frozen=True)
class _ResolvedSource:
    payload: SourcePayload | None
    failure_document: ExtractedSourceDocument | None
    method: str


@dataclass(frozen=True)
class _PreparedClaim:
    sentence_id: str
    reference: ReferenceEntry
    claim: AtomicClaim
    citation_direction: CitationDirection


@dataclass
class _BatchReviewContext:
    total_available: int
    parsed: ParsedDocument
    prepared_claims: list[_PreparedClaim]
    local_context: str
    results: dict[tuple[str, str], RunReviewResponse]
    section_items: list[SectionAnalysisRunItem] | None = None
    section_gate: BatchGateRecommendation | None = None
    section_concurrency_debug: SectionConcurrencyDebug | None = None


@dataclass(frozen=True)
class _SourceGroupRunOutcome:
    results: dict[tuple[str, str], RunReviewResponse]
    timing: BatchSourceWorkerTiming


@dataclass(frozen=True)
class _BatchConcurrencyOutcome:
    results: dict[tuple[str, str], RunReviewResponse]
    debug: BatchConcurrencyDebug


MAX_ACTIVE_BATCH_REVIEWS = 20
_ACTIVE_BATCH_REVIEWS: dict[str, _BatchReviewContext] = {}


class BatchReviewSelection(BaseModel):
    sentence_id: str
    reference_id: str
    approved_claim_text: str | None = None
    citation_direction: CitationDirection | None = None


class BatchReviewItemResponse(BaseModel):
    sentence_id: str
    reference_id: str
    result: RunReviewResponse


class BatchSourceAttention(BaseModel):
    reference_id: str
    canonical_url: str | None = None
    failure_reason: str
    affected_sentence_ids: list[str] = Field(default_factory=list)
    accepted_upload_types: list[str] = Field(
        default_factory=lambda: ["text/html", "application/pdf"]
    )


class BatchSourceWorkerTiming(BaseModel):
    reference_id: str
    claim_count: int
    started_offset_ms: int
    finished_offset_ms: int
    duration_ms: int


class BatchConcurrencyDebug(BaseModel):
    max_concurrent_workers_configured: int
    max_concurrent_workers_seen: int
    total_elapsed_ms: int
    source_workers: list[BatchSourceWorkerTiming] = Field(default_factory=list)


class RunBatchReviewResponse(BaseModel):
    review_id: str
    total_selected: int
    completed_count: int
    awaiting_model_config_count: int
    prejudge_unverified_count: int
    unique_source_count: int
    coverage: BatchCoverage
    gate: BatchGateRecommendation
    concurrency_debug: BatchConcurrencyDebug | None = None
    sources_needing_attention: list[BatchSourceAttention] = Field(default_factory=list)
    items: list[BatchReviewItemResponse] = Field(default_factory=list)


class RunSectionAnalysisResponse(BaseModel):
    review_id: str
    gate: BatchGateRecommendation
    eligible_section_count: int
    completed_count: int
    awaiting_model_config_count: int
    concurrency_debug: SectionConcurrencyDebug
    items: list[SectionAnalysisRunItem] = Field(default_factory=list)


class RunFinalCoherenceResponse(BaseModel):
    review_id: str
    status: str
    gate: BatchGateRecommendation
    packet: FinalCoherencePacket
    assessment: FinalCoherenceAssessment | None = None
    message: str | None = None


async def prepare_review_from_docx(docx_file: UploadFile) -> PrepareReviewResponse:
    content = await docx_file.read()
    try:
        parsed = parse_docx_bytes(docx_file.filename or "report.docx", content)
    except DocxIntakeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PrepareReviewResponse(
        sections=[
            {
                "section_id": section.section_id,
                "heading": section.heading,
                "paragraph_count": len(section.paragraphs),
            }
            for section in parsed.sections
        ],
        references=parsed.references,
        claim_ready_sentences=[
            {
                "sentence_id": sentence.sentence_id,
                "sentence_text": sentence.sentence_text,
                "section_id": sentence.section_id,
                "paragraph_id": sentence.paragraph_id,
                "citation_ids": sentence.citation_ids,
                "reference_ids": sentence.reference_ids,
                "citation_direction": sentence.citation_direction,
                "citation_direction_candidates": [
                    candidate.model_dump(mode="json")
                    for candidate in sentence.citation_direction_candidates
                ],
                "citation_scope_sentences": sentence.citation_scope_sentences,
                "following_context_sentences": sentence.following_context_sentences,
                "requires_citation_direction_confirmation": (
                    sentence.requires_citation_direction_confirmation
                ),
            }
            for sentence in parsed.claim_ready_sentences
        ],
        warnings=parsed.warnings,
    )


async def run_single_claim_review(
    *,
    docx_file: UploadFile,
    source_file: UploadFile | None,
    sentence_id: str,
    reference_id: str,
    approved_claim_text: str | None,
    citation_direction: CitationDirection | None,
    local_context: str,
) -> RunReviewResponse:
    parsed = await _parse_docx_or_400(docx_file)
    return await _run_claim_review_from_parsed(
        parsed=parsed,
        source_file=source_file,
        sentence_id=sentence_id,
        reference_id=reference_id,
        approved_claim_text=approved_claim_text,
        citation_direction=citation_direction,
        local_context=local_context,
    )


async def run_batch_claim_review(
    *,
    docx_file: UploadFile,
    review_pairs_json: str,
    local_context: str,
) -> RunBatchReviewResponse:
    """Run selected claims while fetching each unique cited source once."""

    parsed = await _parse_docx_or_400(docx_file)
    selections = _parse_batch_review_selections(review_pairs_json)

    prepared_claims = [
        _prepare_claim(parsed=parsed, selection=selection) for selection in selections
    ]
    source_groups: dict[str, list[_PreparedClaim]] = {}
    for prepared in prepared_claims:
        source_groups.setdefault(prepared.reference.reference_id, []).append(prepared)

    batch_outcome = await _run_source_groups_with_bounded_concurrency(
        source_groups=list(source_groups.values()),
        local_context=local_context,
    )
    results = batch_outcome.results

    items = [
        BatchReviewItemResponse(
            sentence_id=prepared.sentence_id,
            reference_id=prepared.reference.reference_id,
            result=results[(prepared.sentence_id, prepared.reference.reference_id)],
        )
        for prepared in prepared_claims
    ]

    review_id = f"batch-{uuid4().hex}"
    _store_batch_context(
        review_id,
        _BatchReviewContext(
            total_available=len(parsed.claim_ready_sentences),
            parsed=parsed,
            prepared_claims=prepared_claims,
            local_context=local_context,
            results=results,
        ),
    )
    return _build_batch_response(
        review_id=review_id,
        total_available=len(parsed.claim_ready_sentences),
        unique_source_count=len(source_groups),
        concurrency_debug=batch_outcome.debug,
        items=items,
    )


async def retry_batch_source(
    *,
    review_id: str,
    reference_id: str,
    source_file: UploadFile,
) -> RunBatchReviewResponse:
    context = _ACTIVE_BATCH_REVIEWS.get(review_id)
    if context is None:
        raise HTTPException(
            status_code=404,
            detail="The active batch review was not found. Prepare and run it again.",
        )

    linked_claims = [
        prepared
        for prepared in context.prepared_claims
        if prepared.reference.reference_id == reference_id
    ]
    if not linked_claims:
        raise HTTPException(
            status_code=404,
            detail=f"The batch review has no claims linked to {reference_id}.",
        )

    unresolved_claims = [
        prepared
        for prepared in linked_claims
        if context.results[
            (prepared.sentence_id, prepared.reference.reference_id)
        ].status
        != "completed"
    ]
    if not unresolved_claims or not any(
        _result_needs_source_attention(
            context.results[(prepared.sentence_id, prepared.reference.reference_id)]
        )
        for prepared in unresolved_claims
    ):
        raise HTTPException(
            status_code=400,
            detail="This source does not currently need an uploaded recovery copy.",
        )

    reference = linked_claims[0].reference
    source_id = f"source-{reference.reference_id}"
    resolved_source = await _resolve_uploaded_source_copy(
        reference=reference,
        source_id=source_id,
        source_file=source_file,
    )
    source_document = _source_document_from_resolution(resolved_source)
    for prepared in unresolved_claims:
        context.results[(prepared.sentence_id, prepared.reference.reference_id)] = (
            await _run_prepared_claim_against_source_document(
                prepared=prepared,
                source_document=source_document,
                source_method=resolved_source.method,
                local_context=context.local_context,
            )
        )

    items = [
        BatchReviewItemResponse(
            sentence_id=prepared.sentence_id,
            reference_id=prepared.reference.reference_id,
            result=context.results[
                (prepared.sentence_id, prepared.reference.reference_id)
            ],
        )
        for prepared in context.prepared_claims
    ]
    return _build_batch_response(
        review_id=review_id,
        total_available=context.total_available,
        unique_source_count=len(
            {prepared.reference.reference_id for prepared in context.prepared_claims}
        ),
        items=items,
    )


async def run_batch_section_analysis(*, review_id: str) -> RunSectionAnalysisResponse:
    context = _ACTIVE_BATCH_REVIEWS.get(review_id)
    if context is None:
        raise HTTPException(
            status_code=404,
            detail="The active batch review was not found. Prepare and run it again.",
        )

    batch_items = _batch_items_from_context(context)
    gate = _build_batch_gate_recommendation(batch_items)
    if gate.status in {"stop_and_fix", "review_incomplete"}:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot start section analysis until the evidence gate is clear enough "
                "to continue."
            ),
        )

    packets = build_section_packets(
        parsed=context.parsed,
        claim_outcomes=_build_section_claim_outcomes(context),
        gate=gate,
    )
    outcome = await run_section_packets_with_bounded_concurrency(packets=packets)
    response = RunSectionAnalysisResponse(
        review_id=review_id,
        gate=gate,
        eligible_section_count=len(packets),
        completed_count=sum(1 for item in outcome.items if item.status == "completed"),
        awaiting_model_config_count=sum(
            1 for item in outcome.items if item.status == "awaiting_model_config"
        ),
        concurrency_debug=outcome.concurrency_debug,
        items=outcome.items,
    )
    context.section_items = response.items
    context.section_gate = gate
    context.section_concurrency_debug = response.concurrency_debug
    return response


async def run_batch_final_coherence(*, review_id: str) -> RunFinalCoherenceResponse:
    context = _ACTIVE_BATCH_REVIEWS.get(review_id)
    if context is None:
        raise HTTPException(
            status_code=404,
            detail="The active batch review was not found. Prepare and run it again.",
        )
    if not context.section_items or context.section_gate is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot start final coherence analysis until section analysis has "
                "been run successfully."
            ),
        )
    if any(item.status != "completed" or item.assessment is None for item in context.section_items):
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot start final coherence analysis until all eligible section "
                "workers have completed successfully."
            ),
        )

    batch_items = _batch_items_from_context(context)
    coverage = _build_batch_coverage(
        total_available=context.total_available,
        items=batch_items,
    )
    packet = build_final_coherence_packet(
        review_id=review_id,
        gate=context.section_gate,
        coverage=coverage,
        section_items=context.section_items,
    )
    try:
        assessment = await run_final_coherence(packet=packet)
    except FinalCoherenceConfigurationError as exc:
        return RunFinalCoherenceResponse(
            review_id=review_id,
            status="awaiting_model_config",
            gate=context.section_gate,
            packet=packet,
            message=str(exc),
        )

    return RunFinalCoherenceResponse(
        review_id=review_id,
        status="completed",
        gate=context.section_gate,
        packet=packet,
        assessment=assessment,
    )


async def _run_source_groups_with_bounded_concurrency(
    *,
    source_groups: list[list[_PreparedClaim]],
    local_context: str,
) -> _BatchConcurrencyOutcome:
    """Run one worker per unique source, capped to protect the local app.

    Claims that share a source stay sequential inside the worker so source
    extraction is reused, while unrelated sources can overlap.
    """

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SOURCE_WORKERS)
    started_at = perf_counter()
    active_workers = 0
    max_workers_seen = 0

    async def _bounded_worker(
        source_group: list[_PreparedClaim],
    ) -> _SourceGroupRunOutcome:
        nonlocal active_workers, max_workers_seen
        async with semaphore:
            active_workers += 1
            max_workers_seen = max(max_workers_seen, active_workers)
            worker_started_at = perf_counter()
            try:
                results = await _run_single_source_group(
                    source_group=source_group,
                    local_context=local_context,
                )
            finally:
                worker_finished_at = perf_counter()
                active_workers -= 1
            first_claim = source_group[0]
            return _SourceGroupRunOutcome(
                results=results,
                timing=BatchSourceWorkerTiming(
                    reference_id=first_claim.reference.reference_id,
                    claim_count=len(source_group),
                    started_offset_ms=round((worker_started_at - started_at) * 1000),
                    finished_offset_ms=round((worker_finished_at - started_at) * 1000),
                    duration_ms=round((worker_finished_at - worker_started_at) * 1000),
                ),
            )

    group_outcomes = await asyncio.gather(
        *[
            asyncio.create_task(_bounded_worker(source_group))
            for source_group in source_groups
        ]
    )

    results: dict[tuple[str, str], RunReviewResponse] = {}
    timings: list[BatchSourceWorkerTiming] = []
    for group_outcome in group_outcomes:
        results.update(group_outcome.results)
        timings.append(group_outcome.timing)
    timings.sort(key=lambda timing: (timing.started_offset_ms, timing.reference_id))
    finished_at = perf_counter()
    return _BatchConcurrencyOutcome(
        results=results,
        debug=BatchConcurrencyDebug(
            max_concurrent_workers_configured=MAX_CONCURRENT_SOURCE_WORKERS,
            max_concurrent_workers_seen=max_workers_seen,
            total_elapsed_ms=round((finished_at - started_at) * 1000),
            source_workers=timings,
        ),
    )


async def _run_single_source_group(
    *,
    source_group: list[_PreparedClaim],
    local_context: str,
) -> dict[tuple[str, str], RunReviewResponse]:
    """Fetch/extract one source, then review each linked claim independently."""

    reference = source_group[0].reference
    source_id = f"source-{reference.reference_id}"
    resolved_source = await _resolve_source_payload(
        reference=reference,
        source_id=source_id,
        source_file=None,
    )
    source_document = _source_document_from_resolution(resolved_source)

    results: dict[tuple[str, str], RunReviewResponse] = {}
    for prepared in source_group:
        results[(prepared.sentence_id, prepared.reference.reference_id)] = (
            await _run_prepared_claim_against_source_document(
                prepared=prepared,
                source_document=source_document,
                source_method=resolved_source.method,
                local_context=local_context,
            )
        )
    return results


def _store_batch_context(review_id: str, context: _BatchReviewContext) -> None:
    """Keep only a small in-memory shelf of active local reviews."""

    _ACTIVE_BATCH_REVIEWS[review_id] = context
    while len(_ACTIVE_BATCH_REVIEWS) > MAX_ACTIVE_BATCH_REVIEWS:
        oldest_review_id = next(iter(_ACTIVE_BATCH_REVIEWS))
        del _ACTIVE_BATCH_REVIEWS[oldest_review_id]


def _build_batch_response(
    *,
    review_id: str,
    total_available: int,
    unique_source_count: int,
    concurrency_debug: BatchConcurrencyDebug | None = None,
    items: list[BatchReviewItemResponse],
) -> RunBatchReviewResponse:
    coverage = _build_batch_coverage(total_available=total_available, items=items)
    completed_count = coverage.completed
    attention_by_reference: dict[str, BatchSourceAttention] = {}
    for item in items:
        trace = item.result.trace
        if trace is None or not _trace_needs_source_attention(trace):
            continue
        attention = attention_by_reference.get(item.reference_id)
        if attention is None:
            attention = BatchSourceAttention(
                reference_id=item.reference_id,
                canonical_url=trace.canonical_url,
                failure_reason=(
                    trace.source_failure_reason
                    or "The cited source needs a readable uploaded copy."
                ),
            )
            attention_by_reference[item.reference_id] = attention
        attention.affected_sentence_ids.append(item.sentence_id)

    selected = len(items)
    gate = _build_batch_gate_recommendation(items)
    return RunBatchReviewResponse(
        review_id=review_id,
        total_selected=selected,
        completed_count=completed_count,
        awaiting_model_config_count=sum(
            1 for item in items if item.result.status == "awaiting_model_config"
        ),
        prejudge_unverified_count=sum(
            1 for item in items if item.result.status == "prejudge_unverified"
        ),
        unique_source_count=unique_source_count,
        gate=gate,
        concurrency_debug=concurrency_debug,
        coverage=coverage,
        sources_needing_attention=list(attention_by_reference.values()),
        items=items,
    )


def _batch_items_from_context(
    context: _BatchReviewContext,
) -> list[BatchReviewItemResponse]:
    return [
        BatchReviewItemResponse(
            sentence_id=prepared.sentence_id,
            reference_id=prepared.reference.reference_id,
            result=context.results[(prepared.sentence_id, prepared.reference.reference_id)],
        )
        for prepared in context.prepared_claims
    ]


def _build_batch_coverage(
    *,
    total_available: int,
    items: list[BatchReviewItemResponse],
) -> BatchCoverage:
    completed_count = sum(1 for item in items if item.result.status == "completed")
    verdict_counts: dict[str, int] = {}
    for item in items:
        assessment = item.result.assessment or {}
        verdict = assessment.get("verdict")
        if verdict:
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    selected = len(items)
    return BatchCoverage(
        total_available=total_available,
        selected=selected,
        completed=completed_count,
        unresolved=selected - completed_count,
        deselected=max(total_available - selected, 0),
        verdict_counts=verdict_counts,
    )


def _build_batch_gate_recommendation(
    items: list[BatchReviewItemResponse],
) -> BatchGateRecommendation:
    contradiction_sentence_ids: list[str] = []
    warning_sentence_ids: list[str] = []
    contradiction_count = 0
    unsupported_count = 0
    unverified_count = 0
    checked_claim_count = 0

    for item in items:
        assessment = item.result.assessment or {}
        raw_verdict = assessment.get("verdict")
        if not raw_verdict:
            continue
        checked_claim_count += 1
        verdict = EvidenceVerdict(raw_verdict)
        if verdict == EvidenceVerdict.CONTRADICTED:
            contradiction_count += 1
            contradiction_sentence_ids.append(item.sentence_id)
        elif verdict == EvidenceVerdict.UNSUPPORTED:
            unsupported_count += 1
            warning_sentence_ids.append(item.sentence_id)
        elif verdict == EvidenceVerdict.UNVERIFIED:
            unverified_count += 1
            warning_sentence_ids.append(item.sentence_id)

    pending_claim_count = max(len(items) - checked_claim_count, 0)
    if contradiction_count > 0:
        status = "stop_and_fix"
        summary = (
            f"Stop and fix evidence issues first: {contradiction_count} checked "
            "claim(s) are contradicted."
        )
    elif pending_claim_count > 0:
        status = "review_incomplete"
        summary = (
            f"Evidence review is incomplete: {pending_claim_count} selected claim(s) "
            "still have no evidence outcome."
        )
    elif unsupported_count > 0 or unverified_count > 0:
        status = "continue_with_warnings"
        summary = (
            "No contradictions were found in checked claims, but warnings remain: "
            f"{unsupported_count} unsupported and {unverified_count} unverified."
        )
    else:
        status = "continue"
        summary = (
            "No contradictions, unsupported findings, or unverified findings were "
            "returned for the checked claims."
        )

    return BatchGateRecommendation(
        status=status,
        summary=summary,
        checked_claim_count=checked_claim_count,
        pending_claim_count=pending_claim_count,
        contradiction_count=contradiction_count,
        unsupported_count=unsupported_count,
        unverified_count=unverified_count,
        contradiction_sentence_ids=contradiction_sentence_ids,
        warning_sentence_ids=warning_sentence_ids,
    )


def _trace_needs_source_attention(trace: ReviewTrace) -> bool:
    return (
        trace.source_fetch_status == SourceFetchStatus.FAILED
        or trace.source_extraction_status
        in {
            SourceExtractionStatus.OCR_REQUIRED,
            SourceExtractionStatus.EXTRACTION_FAILED,
        }
    )


def _result_needs_source_attention(result: RunReviewResponse) -> bool:
    return result.trace is not None and _trace_needs_source_attention(result.trace)


def _build_section_claim_outcomes(
    context: _BatchReviewContext,
) -> list[SectionClaimOutcome]:
    section_claim_outcomes: list[SectionClaimOutcome] = []
    for prepared in context.prepared_claims:
        result = context.results[(prepared.sentence_id, prepared.reference.reference_id)]
        assessment = result.assessment or {}
        verdict = assessment.get("verdict")
        if not verdict:
            continue
        sentence = _find_sentence(context.parsed, prepared.sentence_id)
        section_claim_outcomes.append(
            SectionClaimOutcome(
                sentence_id=prepared.sentence_id,
                claim_id=prepared.claim.claim_id,
                approved_claim_text=prepared.claim.atomic_claim,
                original_sentence=sentence.sentence_text,
                section_id=prepared.claim.section_id,
                paragraph_id=prepared.claim.paragraph_id,
                citation_ids=prepared.claim.citation_ids,
                reference_id=prepared.reference.reference_id,
                evidence_verdict=verdict,
                evidence_reason=assessment.get(
                    "reason", result.message or "No evidence reason returned."
                ),
                recommended_action=assessment.get(
                    "recommended_action",
                    "Resolve this section claim before relying on it.",
                ),
                linked_passage_ids=assessment.get("passage_ids", []),
                source_fetch_status=assessment.get(
                    "source_fetch_status",
                    result.trace.source_fetch_status if result.trace else "pending",
                ),
                source_extraction_status=assessment.get(
                    "source_extraction_status",
                    result.trace.source_extraction_status if result.trace else "pending",
                ),
                warnings=assessment.get("warnings", []),
            )
        )
    return section_claim_outcomes


async def _run_claim_review_from_parsed(
    *,
    parsed: ParsedDocument,
    source_file: UploadFile | None,
    sentence_id: str,
    reference_id: str,
    approved_claim_text: str | None,
    citation_direction: CitationDirection | None,
    local_context: str,
) -> RunReviewResponse:
    prepared = _prepare_claim(
        parsed=parsed,
        selection=BatchReviewSelection(
            sentence_id=sentence_id,
            reference_id=reference_id,
            approved_claim_text=approved_claim_text,
            citation_direction=citation_direction,
        ),
    )
    source_id = f"source-{prepared.reference.reference_id}"
    resolved_source = await _resolve_source_payload(
        reference=prepared.reference,
        source_id=source_id,
        source_file=source_file,
    )
    return await _run_prepared_claim_against_source_document(
        prepared=prepared,
        source_document=_source_document_from_resolution(resolved_source),
        source_method=resolved_source.method,
        local_context=local_context,
    )


def _prepare_claim(
    *, parsed: ParsedDocument, selection: BatchReviewSelection
) -> _PreparedClaim:
    sentence = _find_sentence(parsed, selection.sentence_id)
    reference = _find_reference(parsed, selection.reference_id)
    _ensure_sentence_reference_match(sentence.reference_ids, reference.reference_id)
    selected_direction, selected_claim_text = _resolve_claim_selection(
        sentence=sentence,
        requested_direction=selection.citation_direction,
        approved_claim_text=selection.approved_claim_text,
    )
    return _PreparedClaim(
        sentence_id=sentence.sentence_id,
        reference=reference,
        claim=AtomicClaim(
            claim_id=f"claim-{sentence.sentence_id}",
            atomic_claim=selected_claim_text,
            original_sentence=selected_claim_text,
            section_id=sentence.section_id,
            paragraph_id=sentence.paragraph_id,
            citation_ids=sentence.citation_ids,
            qualifiers=[],
            decomposition_confidence=None,
        ),
        citation_direction=selected_direction,
    )


async def _run_prepared_claim_against_source_document(
    *,
    prepared: _PreparedClaim,
    source_document: ExtractedSourceDocument,
    source_method: str,
    local_context: str,
) -> RunReviewResponse:
    claim = prepared.claim
    reference = prepared.reference
    selected_direction = prepared.citation_direction
    deterministic_result = run_deterministic_evidence_review_from_document(
        DeterministicReviewFromDocumentRequest(
            claim=claim,
            source_document=source_document,
            local_context=local_context,
        )
    )

    if deterministic_result.source_document is None:
        raise HTTPException(
            status_code=500,
            detail="Deterministic review did not preserve its source document for audit.",
        )

    if deterministic_result.assessment is not None:
        return RunReviewResponse(
            status="prejudge_unverified",
            assessment=deterministic_result.assessment.model_dump(mode="json"),
            trace=_build_review_trace(
                claim=claim,
                citation_direction=selected_direction,
                reference=reference,
                source_method=source_method,
                stopped_stage=_prejudge_stopped_stage(
                    deterministic_result.source_document
                ),
                model_called=False,
                source_document=deterministic_result.source_document,
                candidate_passages=deterministic_result.candidate_passages,
            ),
        )

    if deterministic_result.judge_payload is None:
        raise HTTPException(status_code=500, detail="Deterministic review produced no assessment and no judge payload.")

    try:
        final_assessment = await judge_evidence_payload(
            deterministic_result.judge_payload
        )
    except JudgeConfigurationError as exc:
        return RunReviewResponse(
            status="awaiting_model_config",
            judge_payload=deterministic_result.judge_payload.model_dump(mode="json"),
            message=str(exc),
            trace=_build_review_trace(
                claim=claim,
                citation_direction=selected_direction,
                reference=reference,
                source_method=source_method,
                stopped_stage="model_configuration",
                model_called=False,
                source_document=deterministic_result.source_document,
                candidate_passages=deterministic_result.candidate_passages,
            ),
        )

    return RunReviewResponse(
        status="completed",
        judge_payload=deterministic_result.judge_payload.model_dump(mode="json"),
        assessment=final_assessment.model_dump(mode="json"),
        trace=_build_review_trace(
            claim=claim,
            citation_direction=selected_direction,
            reference=reference,
            source_method=source_method,
            stopped_stage="completed",
            model_called=True,
            source_document=deterministic_result.source_document,
            candidate_passages=deterministic_result.candidate_passages,
        ),
    )


async def _parse_docx_or_400(docx_file: UploadFile) -> ParsedDocument:
    content = await docx_file.read()
    try:
        return parse_docx_bytes(docx_file.filename or "report.docx", content)
    except DocxIntakeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _find_sentence(parsed: ParsedDocument, sentence_id: str):
    for sentence in parsed.claim_ready_sentences:
        if sentence.sentence_id == sentence_id:
            return sentence
    raise HTTPException(status_code=404, detail=f"Unknown sentence_id: {sentence_id}")


def _find_reference(parsed: ParsedDocument, reference_id: str) -> ReferenceEntry:
    for reference in parsed.references:
        if reference.reference_id == reference_id:
            return reference
    raise HTTPException(status_code=404, detail=f"Unknown reference_id: {reference_id}")


def _ensure_sentence_reference_match(reference_ids: list[str], reference_id: str) -> None:
    if reference_id not in reference_ids:
        raise HTTPException(
            status_code=400,
            detail="The selected sentence is not linked to the selected reference.",
        )


def _strip_citation_markers(text: str) -> str:
    cleaned = CITATION_MARKER_RE.sub("", text)
    return " ".join(cleaned.split())


def _resolve_claim_selection(
    *,
    sentence: ClaimReadySentence,
    requested_direction: CitationDirection | None,
    approved_claim_text: str | None,
) -> tuple[CitationDirection, str]:
    direction = sentence.citation_direction
    candidates = {
        candidate.direction: candidate.sentence_text
        for candidate in sentence.citation_direction_candidates
    }

    if sentence.requires_citation_direction_confirmation:
        if requested_direction not in {
            CitationDirection.BACKWARD,
            CitationDirection.FORWARD,
            CitationDirection.BOTH,
        }:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This citation sits between two sentences. Confirm whether it "
                    "supports the previous sentence, the next sentence, or both."
                ),
            )
        direction = requested_direction

    if approved_claim_text and approved_claim_text.strip():
        return direction, approved_claim_text.strip()

    if direction == CitationDirection.BOTH:
        selected_text = " ".join(
            text
            for candidate_direction in (
                CitationDirection.BACKWARD,
                CitationDirection.FORWARD,
            )
            if (text := candidates.get(candidate_direction))
        )
    else:
        selected_text = candidates.get(direction) or _strip_citation_markers(
            sentence.sentence_text
        )

    if not selected_text.strip():
        raise HTTPException(
            status_code=400,
            detail="The selected citation direction did not produce a reviewable claim.",
        )
    return direction, selected_text.strip()


def _parse_batch_review_selections(review_pairs_json: str) -> list[BatchReviewSelection]:
    try:
        raw_payload = json.loads(review_pairs_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="review_pairs_json must be valid JSON.") from exc

    if not isinstance(raw_payload, list) or not raw_payload:
        raise HTTPException(
            status_code=400,
            detail="review_pairs_json must be a non-empty JSON array of sentence/reference selections.",
        )
    try:
        selections = [
            BatchReviewSelection.model_validate(item) for item in raw_payload
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Each batch review selection must include sentence_id and reference_id.",
        ) from exc
    selection_keys = [
        (selection.sentence_id, selection.reference_id) for selection in selections
    ]
    if len(selection_keys) != len(set(selection_keys)):
        raise HTTPException(
            status_code=400,
            detail="Each sentence/reference pair may be selected only once.",
        )
    return selections


async def _resolve_source_payload(
    *,
    reference: ReferenceEntry,
    source_id: str,
    source_file: UploadFile | None,
) -> _ResolvedSource:
    if source_file is not None:
        source_bytes = await source_file.read()
        if source_bytes:
            return _ResolvedSource(
                payload=SourcePayload(
                    source_id=source_id,
                    reference=reference,
                    body=source_bytes,
                    content_type=source_file.content_type,
                ),
                failure_document=None,
                method="uploaded_source_copy",
            )

    fetch_outcome = await asyncio.to_thread(fetch_exact_source, reference, source_id)
    if fetch_outcome.payload is not None:
        return _ResolvedSource(
            payload=fetch_outcome.payload,
            failure_document=None,
            method="exact_url_fetch",
        )
    if settings.browser_render_enabled and should_try_browser_fallback(
        reference, fetch_outcome
    ):
        browser_outcome = await asyncio.to_thread(
            fetch_rendered_exact_source,
            reference,
            source_id,
        )
        if browser_outcome.payload is not None:
            return _ResolvedSource(
                payload=browser_outcome.payload,
                failure_document=None,
                method="browser_rendered_fetch",
            )
        fetch_outcome = browser_outcome
    if fetch_outcome.failure_document is None:
        raise HTTPException(
            status_code=500,
            detail="Source fetch produced no payload and no failure document.",
        )

    return _ResolvedSource(
        payload=None,
        failure_document=fetch_outcome.failure_document,
        method="exact_url_fetch",
    )


async def _resolve_uploaded_source_copy(
    *,
    reference: ReferenceEntry,
    source_id: str,
    source_file: UploadFile,
) -> _ResolvedSource:
    source_bytes = await source_file.read()
    if not source_bytes:
        raise HTTPException(status_code=400, detail="The uploaded source copy is empty.")

    content_type = (source_file.content_type or "").split(";", 1)[0].lower()
    filename = (source_file.filename or "").lower()
    if content_type == "application/pdf" or filename.endswith(".pdf"):
        source_kind = SourceKind.TEXT_PDF
        content_type = "application/pdf"
    elif content_type in {"text/html", "application/xhtml+xml"} or filename.endswith(
        (".html", ".htm")
    ):
        source_kind = SourceKind.HTML
        content_type = "text/html"
    else:
        raise HTTPException(
            status_code=400,
            detail="Upload an HTML file or a text-extractable PDF copy of the cited source.",
        )

    return _ResolvedSource(
        payload=SourcePayload(
            source_id=source_id,
            reference=reference.model_copy(update={"source_kind": source_kind}),
            body=source_bytes,
            content_type=content_type,
        ),
        failure_document=None,
        method="uploaded_source_copy",
    )


def _source_document_from_resolution(
    resolved_source: _ResolvedSource,
) -> ExtractedSourceDocument:
    if resolved_source.failure_document is not None:
        return resolved_source.failure_document
    if resolved_source.payload is not None:
        return extract_source_document(resolved_source.payload)
    raise HTTPException(
        status_code=500,
        detail="Resolved source contained neither a payload nor a failure document.",
    )


def _prejudge_stopped_stage(source_document: ExtractedSourceDocument) -> str:
    source_record = source_document.source_record
    if source_record.fetch_status == SourceFetchStatus.FAILED:
        return "source_fetch"
    if source_record.extraction_status != SourceExtractionStatus.EXTRACTED:
        return "source_extraction"
    return "passage_retrieval"


def _build_review_trace(
    *,
    claim: AtomicClaim,
    citation_direction: CitationDirection,
    reference: ReferenceEntry,
    source_method: str,
    stopped_stage: str,
    model_called: bool,
    source_document: ExtractedSourceDocument,
    candidate_passages: list[EvidencePassage],
) -> ReviewTrace:
    source_record = source_document.source_record
    return ReviewTrace(
        approved_claim=claim.atomic_claim,
        citation_ids=claim.citation_ids,
        citation_direction=citation_direction,
        reference_id=reference.reference_id,
        canonical_url=source_record.canonical_url or reference.canonical_url,
        source_method=source_method,
        stopped_stage=stopped_stage,
        source_fetch_status=source_record.fetch_status,
        source_extraction_status=source_record.extraction_status,
        source_failure_reason=source_record.failure_reason,
        extracted_block_count=len(source_document.blocks),
        candidate_passage_count=len(candidate_passages),
        candidate_passages=candidate_passages,
        model_called=model_called,
        model_name=settings.default_gemini_model,
    )
