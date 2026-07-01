from __future__ import annotations

from dataclasses import dataclass

from app.review_models import (
    AtomicClaim,
    EvidenceAssessment,
    EvidencePassage,
    EvidenceReviewPayload,
    EvidenceVerdict,
    ExtractedSourceDocument,
    SourceExtractionStatus,
    SourceFetchStatus,
)


class EvidenceInputError(ValueError):
    """Raised when the deterministic side cannot assemble a valid evidence payload."""


@dataclass(frozen=True)
class EvidenceAssemblyRequest:
    claim: AtomicClaim
    source_document: ExtractedSourceDocument
    candidate_passages: list[EvidencePassage]
    local_context: str = ""
    max_passages: int = 5


def assemble_evidence_review_payload(
    request: EvidenceAssemblyRequest,
) -> EvidenceReviewPayload:
    source_record = request.source_document.source_record

    bounded_passages = request.candidate_passages[: request.max_passages]
    if any(
        passage.source_id != source_record.source_id for passage in bounded_passages
    ):
        raise EvidenceInputError(
            "Candidate passages must belong to the same source being reviewed."
        )

    return EvidenceReviewPayload(
        claim_id=request.claim.claim_id,
        atomic_claim=request.claim.atomic_claim,
        original_sentence=request.claim.original_sentence,
        section_id=request.claim.section_id,
        paragraph_id=request.claim.paragraph_id,
        citation_ids=request.claim.citation_ids,
        source_id=source_record.source_id,
        reference_id=source_record.reference_id,
        canonical_url=source_record.canonical_url,
        source_fetch_status=source_record.fetch_status,
        source_extraction_status=source_record.extraction_status,
        source_warnings=request.source_document.warnings,
        local_context=request.local_context,
        candidate_passages=bounded_passages,
    )


def maybe_build_prejudge_unverified_assessment(
    request: EvidenceAssemblyRequest,
) -> EvidenceAssessment | None:
    source_record = request.source_document.source_record

    if source_record.fetch_status == SourceFetchStatus.FAILED:
        return EvidenceAssessment(
            claim_id=request.claim.claim_id,
            source_id=source_record.source_id,
            verdict=EvidenceVerdict.UNVERIFIED,
            reason=source_record.failure_reason
            or "The cited source could not be fetched.",
            recommended_action="Check the citation manually or provide a readable source copy.",
            source_fetch_status=source_record.fetch_status,
            source_extraction_status=source_record.extraction_status,
            warnings=["source_fetch_failed"],
        )

    if source_record.extraction_status == SourceExtractionStatus.OCR_REQUIRED:
        return EvidenceAssessment.unverified_for_ocr_required_pdf(
            claim_id=request.claim.claim_id,
            source_id=source_record.source_id,
        )

    if source_record.extraction_status == SourceExtractionStatus.EXTRACTION_FAILED:
        return EvidenceAssessment(
            claim_id=request.claim.claim_id,
            source_id=source_record.source_id,
            verdict=EvidenceVerdict.UNVERIFIED,
            reason=source_record.failure_reason
            or "The cited source text could not be extracted defensibly.",
            recommended_action="Check the citation manually or provide a cleaner source copy.",
            source_fetch_status=source_record.fetch_status,
            source_extraction_status=source_record.extraction_status,
            warnings=["source_extraction_failed"],
        )

    if not request.candidate_passages:
        return EvidenceAssessment(
            claim_id=request.claim.claim_id,
            source_id=source_record.source_id,
            verdict=EvidenceVerdict.UNVERIFIED,
            reason="Deterministic retrieval did not find enough relevant source passages for a defensible judgment.",
            recommended_action="Review the cited source manually or revise the claim/citation.",
            source_fetch_status=source_record.fetch_status,
            source_extraction_status=source_record.extraction_status,
            warnings=["weak_retrieval_coverage"],
        )

    return None
