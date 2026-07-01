import pytest

import app.final_coherence_judge as final_coherence_judge
from app.config import settings
from app.final_coherence_judge import (
    FinalCoherenceConfigurationError,
    analyze_final_coherence_packet,
)
from app.review_models import (
    FinalCoherenceOutput,
    FinalCoherencePacket,
    FinalSectionDigest,
    ReportCoverageSummary,
)
from tests.unit.test_section_analysis import _gate


@pytest.mark.asyncio
async def test_final_coherence_judge_raises_clear_error_when_env_placeholder_is_not_configured() -> None:
    packet = _coherence_packet()

    original_api_key = settings.google_api_key
    try:
        settings.google_api_key = "PASTE_YOUR_GOOGLE_API_KEY_HERE"
        try:
            await analyze_final_coherence_packet(packet)
        except FinalCoherenceConfigurationError as exc:
            assert "Populate the .env placeholders" in str(exc)
        else:
            raise AssertionError(
                "Expected FinalCoherenceConfigurationError when no real Gemini config is present."
            )
    finally:
        settings.google_api_key = original_api_key


@pytest.mark.asyncio
async def test_final_coherence_judge_maps_adk_output_into_assessment(monkeypatch) -> None:
    async def fake_run_final_coherence_agent(_packet):
        return FinalCoherenceOutput(
            report_summary="The report is mostly aligned but still has one repeated weakness.",
            coherence_strengths=["The sections tell a consistent topline story."],
            coherence_issues=["One later section weakens the earlier claim framing."],
            soundness_issues=["A warning-level metric is still presented too confidently."],
            noteworthy_patterns=["The same overstatement appears in more than one section."],
            priority_actions=["Tone down unsupported certainty before delivery."],
            unresolved_risks=["One warning remains visible at report level."],
            needs_human_attention=True,
        )

    monkeypatch.setattr(
        final_coherence_judge,
        "_run_final_coherence_agent",
        fake_run_final_coherence_agent,
    )
    original_api_key = settings.google_api_key
    try:
        settings.google_api_key = "test-key"
        assessment = await analyze_final_coherence_packet(_coherence_packet())
    finally:
        settings.google_api_key = original_api_key

    assert assessment.needs_human_attention is True
    assert assessment.priority_actions == ["Tone down unsupported certainty before delivery."]


def _coherence_packet() -> FinalCoherencePacket:
    return FinalCoherencePacket(
        review_id="batch-1",
        global_gate=_gate(status="continue_with_warnings"),
        report_coverage=ReportCoverageSummary(
            selected_claim_count=2,
            completed_claim_count=2,
            unresolved_claim_count=0,
            deselected_claim_count=0,
            contradicted_claim_count=0,
            unsupported_claim_count=1,
            unverified_claim_count=1,
            eligible_section_count=1,
            completed_section_count=1,
            human_attention_section_count=1,
        ),
        section_digests=[
            FinalSectionDigest(
                section_id="section-1",
                heading="Executive Summary",
                order=1,
                checked_claim_count=2,
                contradicted_count=0,
                unsupported_count=1,
                unverified_count=1,
                deselected_count=0,
                section_has_contradiction=False,
                section_has_warning=True,
                needs_human_attention=True,
                summary="The section tells a strong topline story but overstates one metric.",
                factual_strengths=["The core revenue result is supported."],
                factual_gaps=["One supporting KPI is missing."],
                insight_issues=["The draft still sounds too certain."],
                unresolved_risks=["One KPI remains unverified."],
                recommended_revisions=["Qualify the unsupported KPI wording."],
            )
        ],
        unresolved_report_risks=["1 checked claim remains unsupported by cited sources."],
    )
