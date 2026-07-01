from __future__ import annotations

from app.final_coherence import build_final_coherence_packet
from app.review_models import BatchCoverage, BatchGateRecommendation, SectionAssessment
from app.section_analysis import SectionAnalysisRunItem

from tests.unit.test_section_analysis import _gate, _section_packet


def test_final_coherence_packet_preserves_gate_and_section_risks() -> None:
    packet = build_final_coherence_packet(
        review_id="batch-1",
        gate=BatchGateRecommendation(
            status="continue_with_warnings",
            summary="Warnings remain after evidence review.",
            checked_claim_count=2,
            pending_claim_count=0,
            contradiction_count=0,
            unsupported_count=1,
            unverified_count=1,
            warning_sentence_ids=["sentence-1", "sentence-2"],
        ),
        coverage=BatchCoverage(
            total_available=3,
            selected=2,
            completed=2,
            unresolved=0,
            deselected=1,
            verdict_counts={
                "unsupported": 1,
                "unverified": 1,
            },
        ),
        section_items=[
            _section_item(
                section_id="section-1",
                order=1,
                heading="Executive Summary",
                unresolved_risks=[
                    "One claim remains unsupported by cited evidence.",
                ],
                needs_human_attention=True,
            )
        ],
    )

    assert packet.global_gate.status == "continue_with_warnings"
    assert packet.report_coverage.unsupported_claim_count == 1
    assert packet.report_coverage.unverified_claim_count == 1
    assert packet.report_coverage.human_attention_section_count == 1
    assert packet.section_digests[0].heading == "Executive Summary"
    assert any("unsupported" in risk.lower() for risk in packet.unresolved_report_risks)
    assert any("human attention" in risk.lower() for risk in packet.unresolved_report_risks)


def test_final_coherence_packet_stays_bounded_and_omits_raw_section_text() -> None:
    packet = build_final_coherence_packet(
        review_id="batch-2",
        gate=_gate(status="continue"),
        coverage=BatchCoverage(
            total_available=2,
            selected=1,
            completed=1,
            unresolved=0,
            deselected=1,
            verdict_counts={"supported_by_cited_source": 1},
        ),
        section_items=[
            _section_item(
                section_id="section-1",
                order=1,
                heading="Findings",
                unresolved_risks=[],
                needs_human_attention=False,
            )
        ],
    )

    dumped = packet.model_dump()
    digest = dumped["section_digests"][0]
    assert "section_text" not in str(dumped)
    assert "subchunks" not in digest
    assert "checked_claims" not in digest
    assert digest["summary"] == "Section summary for Findings."


def _section_item(
    *,
    section_id: str,
    order: int,
    heading: str,
    unresolved_risks: list[str],
    needs_human_attention: bool,
) -> SectionAnalysisRunItem:
    packet = _section_packet(section_id=section_id, order=order)
    packet.heading = heading
    return SectionAnalysisRunItem(
        section_id=section_id,
        status="completed",
        packet=packet,
        assessment=SectionAssessment(
            section_id=section_id,
            heading=heading,
            order=order,
            summary=f"Section summary for {heading}.",
            factual_strengths=["Supported section fact."],
            factual_gaps=[],
            insight_issues=[],
            unresolved_risks=unresolved_risks,
            recommended_revisions=[],
            needs_human_attention=needs_human_attention,
        ),
    )
