from __future__ import annotations

import asyncio

import pytest

import app.review_api as review_api
from app.review_models import (
    AtomicClaim,
    CitationDirection,
    EvidenceVerdict,
    ReferenceEntry,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
)


def _prepared_claim(*, sentence_id: str, reference_id: str) -> review_api._PreparedClaim:
    reference = ReferenceEntry(
        reference_id=reference_id,
        citation_label=f"[{reference_id}]",
        raw_bibliography_text=f"{reference_id} bibliography entry",
        canonical_url=f"https://example.com/{reference_id}",
        source_kind=SourceKind.HTML,
    )
    claim = AtomicClaim(
        claim_id=f"claim-{sentence_id}",
        atomic_claim=f"Claim for {sentence_id}",
        original_sentence=f"Claim for {sentence_id}",
        section_id="section-1",
        paragraph_id="paragraph-1",
        citation_ids=[f"citation-{sentence_id}"],
    )
    return review_api._PreparedClaim(
        sentence_id=sentence_id,
        reference=reference,
        claim=claim,
        citation_direction=CitationDirection.BACKWARD,
    )


def _batch_item(
    *,
    sentence_id: str,
    reference_id: str,
    status: str = "completed",
    verdict: EvidenceVerdict | None = None,
) -> review_api.BatchReviewItemResponse:
    assessment = None
    if verdict is not None:
        assessment = {
            "claim_id": f"claim-{sentence_id}",
            "source_id": f"source-{reference_id}",
            "verdict": verdict.value,
            "reason": f"{verdict.value} reason",
            "recommended_action": "Review this claim.",
            "source_fetch_status": SourceFetchStatus.FETCHED.value,
            "source_extraction_status": SourceExtractionStatus.EXTRACTED.value,
            "passage_ids": [],
            "warnings": [],
        }
    return review_api.BatchReviewItemResponse(
        sentence_id=sentence_id,
        reference_id=reference_id,
        result=review_api.RunReviewResponse(status=status, assessment=assessment),
    )


@pytest.mark.asyncio
async def test_source_group_workers_respect_max_concurrency(monkeypatch) -> None:
    active_workers = 0
    max_seen = 0

    async def fake_run_single_source_group(
        *,
        source_group: list[review_api._PreparedClaim],
        local_context: str,
    ) -> dict[tuple[str, str], review_api.RunReviewResponse]:
        nonlocal active_workers, max_seen
        del local_context
        active_workers += 1
        max_seen = max(max_seen, active_workers)
        try:
            await asyncio.sleep(0.01)
            prepared = source_group[0]
            return {
                (prepared.sentence_id, prepared.reference.reference_id): review_api.RunReviewResponse(
                    status="awaiting_model_config"
                )
            }
        finally:
            active_workers -= 1

    monkeypatch.setattr(
        review_api,
        "_run_single_source_group",
        fake_run_single_source_group,
    )

    source_groups = [
        [_prepared_claim(sentence_id=f"sentence-{index}", reference_id=f"reference-{index}")]
        for index in range(6)
    ]

    outcome = await review_api._run_source_groups_with_bounded_concurrency(
        source_groups=source_groups,
        local_context="",
    )

    assert len(outcome.results) == 6
    assert max_seen == review_api.MAX_CONCURRENT_SOURCE_WORKERS
    assert (
        outcome.debug.max_concurrent_workers_seen
        == review_api.MAX_CONCURRENT_SOURCE_WORKERS
    )
    assert (
        outcome.debug.max_concurrent_workers_configured
        == review_api.MAX_CONCURRENT_SOURCE_WORKERS
    )
    assert len(outcome.debug.source_workers) == 6


@pytest.mark.asyncio
async def test_single_source_group_reuses_one_resolved_document(monkeypatch) -> None:
    prepared_one = _prepared_claim(sentence_id="sentence-1", reference_id="reference-1")
    prepared_two = _prepared_claim(sentence_id="sentence-2", reference_id="reference-1")

    resolved_source = review_api._ResolvedSource(
        payload=None,
        failure_document=object(),  # type: ignore[arg-type]
        method="exact_url_fetch",
    )
    source_document = object()

    resolve_calls = 0
    run_calls: list[tuple[str, object]] = []

    async def fake_resolve_source_payload(
        *,
        reference: ReferenceEntry,
        source_id: str,
        source_file,
    ) -> review_api._ResolvedSource:
        nonlocal resolve_calls
        del reference, source_id, source_file
        resolve_calls += 1
        return resolved_source

    def fake_source_document_from_resolution(
        resolution: review_api._ResolvedSource,
    ) -> object:
        assert resolution is resolved_source
        return source_document

    async def fake_run_prepared_claim_against_source_document(
        *,
        prepared: review_api._PreparedClaim,
        source_document: object,
        source_method: str,
        local_context: str,
    ) -> review_api.RunReviewResponse:
        del source_method, local_context
        run_calls.append((prepared.sentence_id, source_document))
        return review_api.RunReviewResponse(status="awaiting_model_config")

    monkeypatch.setattr(review_api, "_resolve_source_payload", fake_resolve_source_payload)
    monkeypatch.setattr(
        review_api,
        "_source_document_from_resolution",
        fake_source_document_from_resolution,
    )
    monkeypatch.setattr(
        review_api,
        "_run_prepared_claim_against_source_document",
        fake_run_prepared_claim_against_source_document,
    )

    results = await review_api._run_single_source_group(
        source_group=[prepared_one, prepared_two],
        local_context="",
    )

    assert resolve_calls == 1
    assert run_calls == [
        ("sentence-1", source_document),
        ("sentence-2", source_document),
    ]
    assert set(results) == {
        ("sentence-1", "reference-1"),
        ("sentence-2", "reference-1"),
    }


def test_batch_gate_stops_when_any_checked_claim_is_contradicted() -> None:
    gate = review_api._build_batch_gate_recommendation(
        [
            _batch_item(
                sentence_id="sentence-1",
                reference_id="reference-1",
                verdict=EvidenceVerdict.CONTRADICTED,
            ),
            _batch_item(
                sentence_id="sentence-2",
                reference_id="reference-2",
                verdict=EvidenceVerdict.SUPPORTED,
            ),
        ]
    )

    assert gate.status == "stop_and_fix"
    assert gate.checked_claim_count == 2
    assert gate.pending_claim_count == 0
    assert gate.contradiction_count == 1
    assert gate.contradiction_sentence_ids == ["sentence-1"]


def test_batch_gate_keeps_warning_only_when_findings_are_unsupported_or_unverified() -> None:
    gate = review_api._build_batch_gate_recommendation(
        [
            _batch_item(
                sentence_id="sentence-1",
                reference_id="reference-1",
                verdict=EvidenceVerdict.UNSUPPORTED,
            ),
            _batch_item(
                sentence_id="sentence-2",
                reference_id="reference-2",
                status="prejudge_unverified",
                verdict=EvidenceVerdict.UNVERIFIED,
            ),
        ]
    )

    assert gate.status == "continue_with_warnings"
    assert gate.checked_claim_count == 2
    assert gate.pending_claim_count == 0
    assert gate.unsupported_count == 1
    assert gate.unverified_count == 1
    assert gate.warning_sentence_ids == ["sentence-1", "sentence-2"]


def test_batch_gate_marks_review_incomplete_when_selected_claims_lack_evidence_outcomes() -> None:
    gate = review_api._build_batch_gate_recommendation(
        [
            _batch_item(
                sentence_id="sentence-1",
                reference_id="reference-1",
                verdict=EvidenceVerdict.SUPPORTED,
            ),
            _batch_item(
                sentence_id="sentence-2",
                reference_id="reference-2",
                status="awaiting_model_config",
            ),
        ]
    )

    assert gate.status == "review_incomplete"
    assert gate.checked_claim_count == 1
    assert gate.pending_claim_count == 1
