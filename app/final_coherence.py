from __future__ import annotations

from app.final_coherence_judge import (
    FinalCoherenceConfigurationError,
    analyze_final_coherence_packet,
)
from app.review_models import (
    BatchCoverage,
    BatchGateRecommendation,
    FinalCoherenceAssessment,
    FinalCoherencePacket,
    FinalSectionDigest,
    ReportCoverageSummary,
)
from app.section_analysis import SectionAnalysisRunItem


def build_final_coherence_packet(
    *,
    review_id: str,
    gate: BatchGateRecommendation,
    coverage: BatchCoverage,
    section_items: list[SectionAnalysisRunItem],
) -> FinalCoherencePacket:
    completed_sections = [item for item in section_items if item.assessment is not None]
    digests = [
        FinalSectionDigest(
            section_id=item.packet.section_id,
            heading=item.packet.heading,
            order=item.packet.order,
            checked_claim_count=item.packet.coverage_summary.checked_claim_count,
            contradicted_count=item.packet.coverage_summary.contradicted_count,
            unsupported_count=item.packet.coverage_summary.unsupported_count,
            unverified_count=item.packet.coverage_summary.unverified_count,
            deselected_count=item.packet.coverage_summary.deselected_count,
            section_has_contradiction=item.packet.gate_context.section_has_contradiction,
            section_has_warning=item.packet.gate_context.section_has_warning,
            needs_human_attention=item.assessment.needs_human_attention,
            summary=item.assessment.summary,
            factual_strengths=item.assessment.factual_strengths,
            factual_gaps=item.assessment.factual_gaps,
            insight_issues=item.assessment.insight_issues,
            unresolved_risks=item.assessment.unresolved_risks,
            recommended_revisions=item.assessment.recommended_revisions,
        )
        for item in sorted(completed_sections, key=lambda current: current.packet.order)
    ]
    return FinalCoherencePacket(
        review_id=review_id,
        global_gate=gate,
        report_coverage=ReportCoverageSummary(
            selected_claim_count=coverage.selected,
            completed_claim_count=coverage.completed,
            unresolved_claim_count=coverage.unresolved,
            deselected_claim_count=coverage.deselected,
            contradicted_claim_count=gate.contradiction_count,
            unsupported_claim_count=gate.unsupported_count,
            unverified_claim_count=gate.unverified_count,
            eligible_section_count=len(section_items),
            completed_section_count=len(completed_sections),
            human_attention_section_count=sum(
                1
                for item in completed_sections
                if item.assessment and item.assessment.needs_human_attention
            ),
        ),
        section_digests=digests,
        unresolved_report_risks=_build_unresolved_report_risks(
            gate=gate,
            section_items=completed_sections,
        ),
    )


async def run_final_coherence(
    *,
    packet: FinalCoherencePacket,
) -> FinalCoherenceAssessment:
    return await analyze_final_coherence_packet(packet)


def _build_unresolved_report_risks(
    *,
    gate: BatchGateRecommendation,
    section_items: list[SectionAnalysisRunItem],
) -> list[str]:
    risks: list[str] = []
    if gate.contradiction_count > 0:
        risks.append(
            f"{gate.contradiction_count} checked claim(s) remain contradicted by cited sources."
        )
    if gate.unsupported_count > 0:
        risks.append(
            f"{gate.unsupported_count} checked claim(s) remain unsupported by cited sources."
        )
    if gate.unverified_count > 0:
        risks.append(
            f"{gate.unverified_count} checked claim(s) remain unverified because source access or evidence coverage was insufficient."
        )

    human_attention_count = sum(
        1
        for item in section_items
        if item.assessment and item.assessment.needs_human_attention
    )
    if human_attention_count > 0:
        risks.append(
            f"{human_attention_count} section(s) still require human attention after section analysis."
        )

    for item in sorted(section_items, key=lambda current: current.packet.order):
        if not item.assessment:
            continue
        for risk in item.assessment.unresolved_risks:
            report_risk = f"{item.packet.heading}: {risk}"
            if report_risk not in risks:
                risks.append(report_risk)

    return risks[:12]
