from app.evidence_input import (
    EvidenceAssemblyRequest,
    assemble_evidence_review_payload,
    maybe_build_prejudge_unverified_assessment,
)
from app.review_models import (
    AtomicClaim,
    EvidencePassage,
    EvidenceVerdict,
    ExtractedSourceDocument,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
    SourceLocator,
    SourceRecord,
    SourceTextBlock,
)


def test_assemble_evidence_review_payload_keeps_claim_source_and_passage_provenance() -> None:
    claim = _claim()
    document = _document(
        fetch_status=SourceFetchStatus.FETCHED,
        extraction_status=SourceExtractionStatus.EXTRACTED,
    )
    passages = [
        EvidencePassage(
            passage_id="passage-1",
            source_id="source-1",
            text="Revenue grew 12 percent year over year.",
            locator=SourceLocator(heading="Results", text_span_label="html-block-1-chunk-1"),
            retrieval_score=11.0,
        ),
        EvidencePassage(
            passage_id="passage-2",
            source_id="source-1",
            text="Margin improved to 18 percent.",
            locator=SourceLocator(heading="Results", text_span_label="html-block-1-chunk-2"),
            retrieval_score=7.0,
        ),
    ]

    payload = assemble_evidence_review_payload(
        EvidenceAssemblyRequest(
            claim=claim,
            source_document=document,
            candidate_passages=passages,
            local_context="Executive summary",
            max_passages=1,
        )
    )

    assert payload.claim_id == "claim-1"
    assert payload.source_id == "source-1"
    assert payload.candidate_passages[0].passage_id == "passage-1"
    assert payload.local_context == "Executive summary"
    assert len(payload.candidate_passages) == 1


def test_prejudge_unverified_short_circuits_on_weak_retrieval() -> None:
    assessment = maybe_build_prejudge_unverified_assessment(
        EvidenceAssemblyRequest(
            claim=_claim(),
            source_document=_document(
                fetch_status=SourceFetchStatus.FETCHED,
                extraction_status=SourceExtractionStatus.EXTRACTED,
            ),
            candidate_passages=[],
        )
    )

    assert assessment is not None
    assert assessment.verdict == EvidenceVerdict.UNVERIFIED
    assert "weak_retrieval_coverage" in assessment.warnings


def test_prejudge_unverified_short_circuits_on_ocr_required_pdf() -> None:
    assessment = maybe_build_prejudge_unverified_assessment(
        EvidenceAssemblyRequest(
            claim=_claim(),
            source_document=_document(
                fetch_status=SourceFetchStatus.FETCHED,
                extraction_status=SourceExtractionStatus.OCR_REQUIRED,
                source_kind=SourceKind.TEXT_PDF,
                warnings=["ocr_required"],
            ),
            candidate_passages=[],
        )
    )

    assert assessment is not None
    assert assessment.verdict == EvidenceVerdict.UNVERIFIED
    assert assessment.source_extraction_status == SourceExtractionStatus.OCR_REQUIRED
    assert "ocr_required" in assessment.warnings


def _claim() -> AtomicClaim:
    return AtomicClaim(
        claim_id="claim-1",
        atomic_claim="Revenue grew 12 percent year over year.",
        original_sentence="Revenue grew 12 percent year over year.[1]",
        section_id="section-1",
        paragraph_id="paragraph-1",
        citation_ids=["citation-1"],
    )


def _document(
    *,
    fetch_status: SourceFetchStatus,
    extraction_status: SourceExtractionStatus,
    source_kind: SourceKind = SourceKind.HTML,
    warnings: list[str] | None = None,
) -> ExtractedSourceDocument:
    return ExtractedSourceDocument(
        source_record=SourceRecord(
            source_id="source-1",
            reference_id="reference-1",
            source_kind=source_kind,
            canonical_url="https://example.com/report",
            fetch_status=fetch_status,
            extraction_status=extraction_status,
            failure_reason=(
                "The cited source text could not be extracted defensibly."
                if extraction_status == SourceExtractionStatus.EXTRACTION_FAILED
                else None
            ),
        ),
        blocks=[
            SourceTextBlock(
                block_id="block-1",
                source_id="source-1",
                text="Revenue grew 12 percent year over year.",
                locator=SourceLocator(heading="Results", text_span_label="html-block-1"),
            )
        ],
        warnings=warnings or [],
    )
