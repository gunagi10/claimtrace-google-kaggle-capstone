from app.review_models import (
    CitationMappingStatus,
    DocumentLocator,
    EvidenceAssessment,
    EvidenceVerdict,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
    SourceRecord,
)


def test_evidence_verdict_contract_has_exactly_five_outcomes() -> None:
    assert {verdict.value for verdict in EvidenceVerdict} == {
        "supported_by_cited_source",
        "partially_supported",
        "unsupported",
        "contradicted",
        "unverified",
    }


def test_source_record_blocks_evidence_when_ocr_is_required() -> None:
    source = SourceRecord(
        source_id="src-1",
        reference_id="ref-1",
        source_kind=SourceKind.TEXT_PDF,
        fetch_status=SourceFetchStatus.FETCHED,
        extraction_status=SourceExtractionStatus.OCR_REQUIRED,
        failure_reason="No text layer detected",
    )

    assert source.blocks_evidence_review() is True


def test_unverified_assessment_for_ocr_required_pdf_is_explicit() -> None:
    assessment = EvidenceAssessment.unverified_for_ocr_required_pdf(
        claim_id="claim-1",
        source_id="src-1",
    )

    assert assessment.verdict == EvidenceVerdict.UNVERIFIED
    assert assessment.source_extraction_status == SourceExtractionStatus.OCR_REQUIRED
    assert "ocr_required" in assessment.warnings


def test_citation_occurrence_can_keep_document_provenance_shape() -> None:
    locator = DocumentLocator(
        section_id="sec-1",
        paragraph_id="para-1",
        sentence_index=0,
    )

    assert locator.model_dump() == {
        "section_id": "sec-1",
        "paragraph_id": "para-1",
        "sentence_index": 0,
    }

    assert CitationMappingStatus.MAPPED == "mapped"
