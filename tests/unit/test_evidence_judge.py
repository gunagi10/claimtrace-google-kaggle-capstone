import pytest

import app.evidence_judge as evidence_judge
from app.evidence_judge import JudgeConfigurationError, judge_evidence_payload
from app.config import settings
from app.review_models import (
    EvidencePassage,
    EvidenceReviewPayload,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceLocator,
)


@pytest.mark.asyncio
async def test_judge_raises_clear_error_when_env_placeholder_is_not_configured() -> None:
    payload = EvidenceReviewPayload(
        claim_id="claim-1",
        atomic_claim="Revenue grew 12 percent year over year.",
        original_sentence="Revenue grew 12 percent year over year.[1]",
        section_id="section-1",
        paragraph_id="paragraph-1",
        citation_ids=["citation-1"],
        source_id="source-1",
        reference_id="reference-1",
        canonical_url="https://example.com/report",
        source_fetch_status=SourceFetchStatus.FETCHED,
        source_extraction_status=SourceExtractionStatus.EXTRACTED,
        candidate_passages=[
            EvidencePassage(
                passage_id="passage-1",
                source_id="source-1",
                text="Revenue grew 12 percent year over year.",
                locator=SourceLocator(heading="Results", text_span_label="block-1"),
            )
        ],
    )

    original_api_key = settings.google_api_key
    try:
        settings.google_api_key = "PASTE_YOUR_GOOGLE_API_KEY_HERE"
        try:
            await judge_evidence_payload(payload)
        except JudgeConfigurationError as exc:
            assert "Populate the .env placeholders" in str(exc)
        else:
            raise AssertionError(
                "Expected JudgeConfigurationError when no real Gemini config is present."
            )
    finally:
        settings.google_api_key = original_api_key


@pytest.mark.asyncio
async def test_judge_maps_adk_output_and_filters_unknown_passage_ids(monkeypatch) -> None:
    payload = EvidenceReviewPayload(
        claim_id="claim-1",
        atomic_claim="Revenue grew 12 percent year over year.",
        original_sentence="Revenue grew 12 percent year over year.[1]",
        section_id="section-1",
        paragraph_id="paragraph-1",
        citation_ids=["citation-1"],
        source_id="source-1",
        reference_id="reference-1",
        canonical_url="https://example.com/report",
        source_fetch_status=SourceFetchStatus.FETCHED,
        source_extraction_status=SourceExtractionStatus.EXTRACTED,
        candidate_passages=[
            EvidencePassage(
                passage_id="passage-1",
                source_id="source-1",
                text="Revenue grew 12 percent year over year.",
                locator=SourceLocator(heading="Results", text_span_label="block-1"),
            )
        ],
    )

    async def fake_run_judge_agent(_payload):
        return evidence_judge.JudgeOutput(
            verdict="supported_by_cited_source",
            reason="The supplied passage states the same result.",
            recommended_action="No change needed.",
            passage_ids=["passage-1", "invented-passage"],
        )

    monkeypatch.setattr(evidence_judge, "_run_judge_agent", fake_run_judge_agent)
    original_api_key = settings.google_api_key
    try:
        settings.google_api_key = "test-key"
        assessment = await judge_evidence_payload(payload)
    finally:
        settings.google_api_key = original_api_key

    assert assessment.verdict == "supported_by_cited_source"
    assert assessment.passage_ids == ["passage-1"]
