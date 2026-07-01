from app.review_models import AtomicClaim, EvidenceVerdict, SourceKind
from app.review_orchestrator import (
    DeterministicReviewRequest,
    run_deterministic_evidence_review,
)
from app.source_adapters import SourcePayload


def test_orchestrator_returns_judge_payload_for_supported_html_path() -> None:
    result = run_deterministic_evidence_review(
        DeterministicReviewRequest(
            claim=_claim(),
            source=SourcePayload(
                source_id="source-1",
                reference=_reference_html(),
                body=(
                    b"<html><body><h1>Results</h1><p>Revenue grew 12 percent year over year.</p>"
                    b"<p>Margin improved to 18 percent.</p></body></html>"
                ),
                content_type="text/html",
            ),
            local_context="Executive summary results",
            top_k_passages=2,
        )
    )

    assert result.assessment is None
    assert result.judge_payload is not None
    assert result.judge_payload.claim_id == "claim-1"
    assert result.judge_payload.source_id == "source-1"
    assert len(result.judge_payload.candidate_passages) >= 1


def test_orchestrator_short_circuits_to_unverified_for_ocr_required_pdf() -> None:
    result = run_deterministic_evidence_review(
        DeterministicReviewRequest(
            claim=_claim(),
            source=SourcePayload(
                source_id="source-2",
                reference=_reference_pdf(),
                body=_blank_pdf_bytes(),
                content_type="application/pdf",
            ),
            local_context="Executive summary results",
        )
    )

    assert result.judge_payload is None
    assert result.assessment is not None
    assert result.assessment.verdict == EvidenceVerdict.UNVERIFIED
    assert "ocr_required" in result.assessment.warnings


def test_orchestrator_short_circuits_to_unverified_for_weak_retrieval() -> None:
    result = run_deterministic_evidence_review(
        DeterministicReviewRequest(
            claim=_claim(),
            source=SourcePayload(
                source_id="source-3",
                reference=_reference_html(),
                body=b"<html><body><h1>Intro</h1><p>General introductory language only.</p></body></html>",
                content_type="text/html",
            ),
            local_context="Executive summary results",
        )
    )

    assert result.judge_payload is None
    assert result.assessment is not None
    assert result.assessment.verdict == EvidenceVerdict.UNVERIFIED
    assert "weak_retrieval_coverage" in result.assessment.warnings


def _claim() -> AtomicClaim:
    return AtomicClaim(
        claim_id="claim-1",
        atomic_claim="Revenue grew 12 percent year over year.",
        original_sentence="Revenue grew 12 percent year over year.[1]",
        section_id="section-1",
        paragraph_id="paragraph-1",
        citation_ids=["citation-1"],
    )


def _reference_html():
    from app.review_models import ReferenceEntry

    return ReferenceEntry(
        reference_id="reference-1",
        citation_label="1",
        raw_bibliography_text="https://example.com/report",
        canonical_url="https://example.com/report",
        source_kind=SourceKind.HTML,
    )


def _reference_pdf():
    from app.review_models import ReferenceEntry

    return ReferenceEntry(
        reference_id="reference-2",
        citation_label="2",
        raw_bibliography_text="https://example.com/report.pdf",
        canonical_url="https://example.com/report.pdf",
        source_kind=SourceKind.TEXT_PDF,
    )


def _blank_pdf_bytes() -> bytes:
    pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
186
%%EOF
"""
    return pdf
