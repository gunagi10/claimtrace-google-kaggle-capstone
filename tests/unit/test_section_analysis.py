from __future__ import annotations

import asyncio

import pytest

import app.section_analysis as section_analysis
from app.review_models import (
    BatchGateRecommendation,
    ClaimReadySentence,
    CitationDirection,
    DocumentParagraph,
    DocumentSection,
    EvidenceVerdict,
    ParsedDocument,
    SectionAssessment,
    SectionClaimOutcome,
)


def test_build_section_packets_excludes_reference_sections() -> None:
    parsed = _parsed_document(
        sections=[
            _section(
                section_id="section-1",
                heading="Executive Summary",
                paragraphs=["Revenue grew 12 percent year over year."],
            ),
            _section(
                section_id="section-2",
                heading="References",
                paragraphs=["[1] https://example.com/report"],
            ),
        ],
        claim_ready_sentences=[
            _claim_ready_sentence("sentence-1", "section-1"),
            _claim_ready_sentence("sentence-2", "section-2"),
        ],
    )

    packets = section_analysis.build_section_packets(
        parsed=parsed,
        claim_outcomes=[
            _claim_outcome(sentence_id="sentence-1", section_id="section-1"),
            _claim_outcome(sentence_id="sentence-2", section_id="section-2"),
        ],
        gate=_gate(status="continue"),
        max_section_words=20,
        max_subchunk_words=10,
    )

    assert [packet.section_id for packet in packets] == ["section-1"]


def test_build_section_packets_subchunks_oversized_sections_with_stable_order() -> None:
    parsed = _parsed_document(
        sections=[
            _section(
                section_id="section-1",
                heading="Findings",
                paragraphs=[
                    "One two three four five six seven eight.",
                    "Nine ten eleven twelve thirteen fourteen fifteen sixteen.",
                    "Seventeen eighteen nineteen twenty twentyone twentytwo twentythree twentyfour.",
                ],
            )
        ],
        claim_ready_sentences=[_claim_ready_sentence("sentence-1", "section-1")],
    )

    packets = section_analysis.build_section_packets(
        parsed=parsed,
        claim_outcomes=[_claim_outcome(sentence_id="sentence-1", section_id="section-1")],
        gate=_gate(status="continue_with_warnings"),
        max_section_words=12,
        max_subchunk_words=8,
    )

    assert len(packets) == 1
    packet = packets[0]
    assert packet.is_oversized is True
    assert [subchunk.order for subchunk in packet.subchunks] == [1, 2, 3]
    assert all(subchunk.subchunk_id.startswith("section-1-subchunk-") for subchunk in packet.subchunks)
    assert "One two three four five six seven eight." in packet.section_text


def test_build_section_packets_keeps_section_scoped_claim_outcomes_and_coverage() -> None:
    parsed = _parsed_document(
        sections=[
            _section(
                section_id="section-1",
                heading="Executive Summary",
                paragraphs=["Revenue grew 12 percent year over year. Margin improved to 18 percent."],
            )
        ],
        claim_ready_sentences=[
            _claim_ready_sentence("sentence-1", "section-1"),
            _claim_ready_sentence("sentence-2", "section-1"),
            _claim_ready_sentence("sentence-3", "section-1"),
        ],
    )

    packets = section_analysis.build_section_packets(
        parsed=parsed,
        claim_outcomes=[
            _claim_outcome(
                sentence_id="sentence-1",
                section_id="section-1",
                verdict=EvidenceVerdict.CONTRADICTED,
            ),
            _claim_outcome(
                sentence_id="sentence-2",
                section_id="section-1",
                verdict=EvidenceVerdict.UNVERIFIED,
            ),
        ],
        gate=_gate(status="continue_with_warnings"),
        max_section_words=100,
        max_subchunk_words=50,
    )

    packet = packets[0]
    assert [claim.sentence_id for claim in packet.checked_claims] == ["sentence-1", "sentence-2"]
    assert packet.coverage_summary.checked_claim_count == 2
    assert packet.coverage_summary.contradicted_count == 1
    assert packet.coverage_summary.unverified_count == 1
    assert packet.coverage_summary.deselected_count == 1
    assert packet.gate_context.global_gate_status == "continue_with_warnings"


@pytest.mark.asyncio
async def test_section_workers_respect_max_concurrency(monkeypatch) -> None:
    active_workers = 0
    max_seen = 0

    async def fake_analyze_section_packet(packet):
        nonlocal active_workers, max_seen
        active_workers += 1
        max_seen = max(max_seen, active_workers)
        try:
            await asyncio.sleep(0.01)
            return SectionAssessment(
                section_id=packet.section_id,
                heading=packet.heading,
                order=packet.order,
                summary=f"Summary for {packet.section_id}",
                factual_strengths=["Supported section fact."],
                factual_gaps=[],
                insight_issues=[],
                unresolved_risks=[],
                recommended_revisions=[],
                needs_human_attention=False,
            )
        finally:
            active_workers -= 1

    monkeypatch.setattr(
        section_analysis,
        "analyze_section_packet",
        fake_analyze_section_packet,
    )

    packets = [
        _section_packet(section_id=f"section-{index}", order=index)
        for index in range(1, 5)
    ]

    outcome = await section_analysis.run_section_packets_with_bounded_concurrency(
        packets=packets,
        max_concurrent_workers=2,
    )

    assert len(outcome.items) == 4
    assert max_seen == 2
    assert outcome.concurrency_debug.max_concurrent_workers_configured == 2
    assert outcome.concurrency_debug.max_concurrent_workers_seen == 2


def _parsed_document(
    *,
    sections: list[DocumentSection],
    claim_ready_sentences: list[ClaimReadySentence],
) -> ParsedDocument:
    return ParsedDocument(
        sections=sections,
        references=[],
        citation_occurrences=[],
        claim_ready_sentences=claim_ready_sentences,
        warnings=[],
    )


def _section(
    *,
    section_id: str,
    heading: str,
    paragraphs: list[str],
) -> DocumentSection:
    return DocumentSection(
        section_id=section_id,
        heading=heading,
        order=int(section_id.split("-")[-1]),
        paragraphs=[
            DocumentParagraph(
                paragraph_id=f"{section_id}-paragraph-{index}",
                section_id=section_id,
                order=index,
                text=text,
            )
            for index, text in enumerate(paragraphs, start=1)
        ],
    )


def _claim_ready_sentence(sentence_id: str, section_id: str) -> ClaimReadySentence:
    return ClaimReadySentence(
        sentence_id=sentence_id,
        sentence_text=f"Sentence text for {sentence_id}.",
        section_id=section_id,
        paragraph_id=f"{section_id}-paragraph-1",
        sentence_index=0,
        citation_ids=[f"citation-{sentence_id}"],
        reference_ids=[f"reference-{sentence_id}"],
        citation_direction=CitationDirection.BACKWARD,
    )


def _claim_outcome(
    *,
    sentence_id: str,
    section_id: str,
    verdict: EvidenceVerdict = EvidenceVerdict.SUPPORTED,
) -> SectionClaimOutcome:
    return SectionClaimOutcome(
        sentence_id=sentence_id,
        claim_id=f"claim-{sentence_id}",
        approved_claim_text=f"Approved claim for {sentence_id}",
        original_sentence=f"Original sentence for {sentence_id}.",
        section_id=section_id,
        paragraph_id=f"{section_id}-paragraph-1",
        citation_ids=[f"citation-{sentence_id}"],
        reference_id=f"reference-{sentence_id}",
        evidence_verdict=verdict,
        evidence_reason=f"Reason for {sentence_id}",
        recommended_action=f"Action for {sentence_id}",
        linked_passage_ids=[f"passage-{sentence_id}"],
        source_fetch_status="fetched",
        source_extraction_status="extracted",
        warnings=[],
    )


def _gate(*, status: str) -> BatchGateRecommendation:
    return BatchGateRecommendation(
        status=status,
        summary=f"Gate summary for {status}",
        checked_claim_count=2,
        pending_claim_count=0,
    )


def _section_packet(*, section_id: str, order: int):
    return section_analysis.build_section_packets(
        parsed=_parsed_document(
            sections=[
                _section(
                    section_id=section_id,
                    heading=f"Heading {section_id}",
                    paragraphs=[f"Text for {section_id}."],
                )
            ],
            claim_ready_sentences=[_claim_ready_sentence(f"sentence-{order}", section_id)],
        ),
        claim_outcomes=[_claim_outcome(sentence_id=f"sentence-{order}", section_id=section_id)],
        gate=_gate(status="continue"),
    )[0]
