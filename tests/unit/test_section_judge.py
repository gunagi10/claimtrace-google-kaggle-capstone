import pytest

import app.section_judge as section_judge
from app.config import settings
from app.review_models import (
    BatchGateRecommendation,
    SectionAnalysisOutput,
    SectionClaimOutcome,
    SectionCoverageSummary,
    SectionGateContext,
    SectionPacket,
    SourceExtractionStatus,
    SourceFetchStatus,
)
from app.section_judge import SectionJudgeConfigurationError, analyze_section_packet


@pytest.mark.asyncio
async def test_section_judge_raises_clear_error_when_env_placeholder_is_not_configured() -> None:
    packet = _section_packet()

    original_api_key = settings.google_api_key
    try:
        settings.google_api_key = "PASTE_YOUR_GOOGLE_API_KEY_HERE"
        try:
            await analyze_section_packet(packet)
        except SectionJudgeConfigurationError as exc:
            assert "Populate the .env placeholders" in str(exc)
        else:
            raise AssertionError(
                "Expected SectionJudgeConfigurationError when no real Gemini config is present."
            )
    finally:
        settings.google_api_key = original_api_key


@pytest.mark.asyncio
async def test_section_judge_maps_adk_output_into_section_assessment(monkeypatch) -> None:
    async def fake_run_section_agent(_packet):
        return SectionAnalysisOutput(
            section_id="section-1",
            summary="A grounded section summary.",
            factual_strengths=["Supported quantitative result."],
            factual_gaps=["One claim needs narrower wording."],
            insight_issues=["The section overstates breadth."],
            unresolved_risks=["One claim remains unverified."],
            recommended_revisions=["Narrow the broad-scope sentence."],
            needs_human_attention=True,
        )

    monkeypatch.setattr(section_judge, "_run_section_agent", fake_run_section_agent)
    original_api_key = settings.google_api_key
    try:
        settings.google_api_key = "test-key"
        assessment = await analyze_section_packet(_section_packet())
    finally:
        settings.google_api_key = original_api_key

    assert assessment.section_id == "section-1"
    assert assessment.heading == "Executive Summary"
    assert assessment.order == 2
    assert assessment.needs_human_attention is True
    assert assessment.recommended_revisions == ["Narrow the broad-scope sentence."]


def _section_packet() -> SectionPacket:
    return SectionPacket(
        section_id="section-1",
        heading="Executive Summary",
        order=2,
        section_text="Revenue grew 12 percent year over year.",
        word_count=6,
        is_oversized=False,
        subchunks=[],
        checked_claims=[
            SectionClaimOutcome(
                sentence_id="sentence-1",
                claim_id="claim-sentence-1",
                approved_claim_text="Revenue grew 12 percent year over year.",
                original_sentence="Revenue grew 12 percent year over year.[1]",
                section_id="section-1",
                paragraph_id="paragraph-1",
                citation_ids=["citation-1"],
                reference_id="reference-1",
                evidence_verdict="supported_by_cited_source",
                evidence_reason="The cited source states the same result.",
                recommended_action="No change needed.",
                linked_passage_ids=["passage-1"],
                source_fetch_status=SourceFetchStatus.FETCHED,
                source_extraction_status=SourceExtractionStatus.EXTRACTED,
                warnings=[],
            )
        ],
        gate_context=SectionGateContext(
            global_gate_status="continue",
            global_gate_summary="No contradictions were found.",
            global_stop_recommended=False,
            section_has_contradiction=False,
            section_has_warning=False,
        ),
        coverage_summary=SectionCoverageSummary(
            checked_claim_count=1,
            contradicted_count=0,
            unsupported_count=0,
            unverified_count=0,
            deselected_count=0,
        ),
        unresolved_risks=[],
        visual_context=[],
    )
