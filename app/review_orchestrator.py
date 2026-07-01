from __future__ import annotations

from dataclasses import dataclass

from app.evidence_input import (
    EvidenceAssemblyRequest,
    assemble_evidence_review_payload,
    maybe_build_prejudge_unverified_assessment,
)
from app.passage_retriever import RetrievalQuery, retrieve_candidate_passages
from app.review_models import (
    AtomicClaim,
    DeterministicReviewOutcome,
    ExtractedSourceDocument,
)
from app.review_models import (
    DeterministicReviewOutcome as _DeterministicReviewOutcome,
)
from app.source_adapters import SourcePayload, extract_source_document


@dataclass(frozen=True)
class DeterministicReviewRequest:
    claim: AtomicClaim
    source: SourcePayload
    local_context: str = ""
    top_k_passages: int = 5
    max_chars_per_passage: int = 420


@dataclass(frozen=True)
class DeterministicReviewFromDocumentRequest:
    claim: AtomicClaim
    source_document: ExtractedSourceDocument
    local_context: str = ""
    top_k_passages: int = 5
    max_chars_per_passage: int = 420


def run_deterministic_evidence_review(
    request: DeterministicReviewRequest,
) -> DeterministicReviewOutcome:
    extracted_document = extract_source_document(request.source)
    return run_deterministic_evidence_review_from_document(
        DeterministicReviewFromDocumentRequest(
            claim=request.claim,
            source_document=extracted_document,
            local_context=request.local_context,
            top_k_passages=request.top_k_passages,
            max_chars_per_passage=request.max_chars_per_passage,
        )
    )


def run_deterministic_evidence_review_from_document(
    request: DeterministicReviewFromDocumentRequest,
) -> DeterministicReviewOutcome:
    extracted_document = request.source_document
    candidate_passages = retrieve_candidate_passages(
        extracted_document,
        RetrievalQuery(
            claim_text=request.claim.atomic_claim,
            local_context=request.local_context,
            top_k=request.top_k_passages,
            max_chars_per_passage=request.max_chars_per_passage,
        ),
    )

    assembly_request = EvidenceAssemblyRequest(
        claim=request.claim,
        source_document=extracted_document,
        candidate_passages=candidate_passages,
        local_context=request.local_context,
        max_passages=request.top_k_passages,
    )

    prejudge_assessment = maybe_build_prejudge_unverified_assessment(assembly_request)
    if prejudge_assessment is not None:
        return _DeterministicReviewOutcome(
            claim_id=request.claim.claim_id,
            source_id=extracted_document.source_record.source_id,
            assessment=prejudge_assessment,
            source_document=extracted_document,
            candidate_passages=candidate_passages,
        )

    judge_payload = assemble_evidence_review_payload(assembly_request)
    return _DeterministicReviewOutcome(
        claim_id=request.claim.claim_id,
        source_id=extracted_document.source_record.source_id,
        judge_payload=judge_payload,
        source_document=extracted_document,
        candidate_passages=candidate_passages,
    )
